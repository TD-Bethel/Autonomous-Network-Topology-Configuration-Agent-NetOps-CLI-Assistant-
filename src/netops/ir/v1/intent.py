"""Versioned, declarative network intent. Keep design logic out of this module."""

from ipaddress import IPv4Address, IPv4Network
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Vlan(BaseModel):
    """A requested broadcast domain; its VLAN ID and prefix are derived."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1, pattern=r"^[a-zA-Z][a-zA-Z0-9_-]*$")
    purpose: Literal["staff", "voice", "guest", "mgmt", "servers"]
    hosts_required: int = Field(gt=0)
    growth_pct: int = Field(default=30, ge=0, le=500)
    dhcp_enabled: bool = True
    dhcp_dns_server: IPv4Address | None = None


class Uplink(BaseModel):
    """A physical point-to-point link whose addresses are compiler-assigned."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    interface: str = Field(min_length=1, pattern=r"^[A-Za-z][A-Za-z0-9./-]*$")
    peer: str = Field(min_length=1, pattern=r"^[A-Za-z][A-Za-z0-9_-]*$")


class Site(BaseModel):
    """A site and the VLANs/uplinks requested at that site."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1, pattern=r"^[a-zA-Z][a-zA-Z0-9_-]*$")
    vlans: list[Vlan] = Field(min_length=1)
    uplinks: list[Uplink] = Field(default_factory=list)


class NetworkIntent(BaseModel):
    """Version 1 compiler input. No assigned IDs or subnets are accepted."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["v1"] = "v1"
    supernet: IPv4Network
    loopback_supernet: IPv4Network
    p2p_supernet: IPv4Network | None = None
    sites: list[Site] = Field(min_length=1, max_length=1)
    security_baseline: str = Field(default="cis-ios", min_length=1)
    ospf_process_id: int = Field(default=1, ge=1, le=65535)
    ospf_area: int = Field(default=0, ge=0, le=4_294_967_295)

    @model_validator(mode="after")
    def validate_address_pools(self) -> "NetworkIntent":
        if self.supernet.overlaps(self.loopback_supernet):
            raise ValueError("loopback_supernet must not overlap the VLAN supernet")
        uplinks = [uplink for site in self.sites for uplink in site.uplinks]
        if uplinks and self.p2p_supernet is None:
            raise ValueError("p2p_supernet is required when uplinks are declared")
        if self.p2p_supernet is not None:
            if self.p2p_supernet.overlaps(self.supernet):
                raise ValueError("p2p_supernet must not overlap the VLAN supernet")
            if self.p2p_supernet.overlaps(self.loopback_supernet):
                raise ValueError("p2p_supernet must not overlap loopback_supernet")
            if len(uplinks) * 2 > self.p2p_supernet.num_addresses:
                raise ValueError("p2p_supernet does not have enough addresses for /31 links")
        interfaces = [uplink.interface.casefold() for uplink in uplinks]
        if len(interfaces) != len(set(interfaces)):
            raise ValueError("uplink interface names must be unique")
        return self
