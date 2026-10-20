"""Brownfield observed-network IR with explicit evidence and freshness policy."""

from datetime import datetime
from ipaddress import (
    IPv4Address,
    IPv4Interface,
    IPv4Network,
    IPv6Address,
    IPv6Interface,
    IPv6Network,
)
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from netops.ir.v1.evidence import EvidenceRef, EvidenceSource
from netops.ir.v1.findings import Confidence, Finding

IPAddressValue = IPv4Address | IPv6Address
IPInterfaceValue = IPv4Interface | IPv6Interface
IPNetworkValue = IPv4Network | IPv6Network


class InterfaceRef(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    device: str = Field(min_length=1)
    interface: str = Field(min_length=1)


class FreshnessPolicy(BaseModel):
    """Consumer policy for deciding whether evidence is still usable."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    max_age_seconds: int = Field(gt=0)
    on_stale: Literal["warn", "block"] = "block"


class ObservedInterface(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1)
    admin_status: Literal["up", "down", "unknown"] = "unknown"
    oper_status: Literal["up", "down", "unknown"] = "unknown"
    mode: Literal["access", "trunk", "routed", "unknown"] = "unknown"
    access_vlan: int | None = Field(default=None, ge=1, le=4094)
    allowed_vlans: list[int] = Field(default_factory=list)
    addresses: list[IPInterfaceValue] = Field(default_factory=list)
    evidence: list[EvidenceRef] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_vlan_fields(self) -> "ObservedInterface":
        if self.mode != "trunk" and self.allowed_vlans:
            raise ValueError("allowed_vlans is only valid for trunk interfaces")
        if self.mode != "access" and self.access_vlan is not None:
            raise ValueError("access_vlan is only valid for access interfaces")
        if len(self.allowed_vlans) != len(set(self.allowed_vlans)):
            raise ValueError("allowed_vlans entries must be unique")
        return self


class ObservedDevice(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1)
    vendor: str = Field(min_length=1)
    platform: str = Field(min_length=1)
    software_version: str | None = None
    interfaces: list[ObservedInterface] = Field(default_factory=list)
    evidence: list[EvidenceRef] = Field(min_length=1)


class ObservedLink(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    endpoint_a: InterfaceRef
    endpoint_b: InterfaceRef
    link_kind: Literal["physical", "logical"] = "physical"
    basis: Literal["direct", "reconciled", "inferred"]
    confidence: Confidence
    evidence: list[EvidenceRef] = Field(min_length=1)

    @model_validator(mode="after")
    def endpoints_must_differ(self) -> "ObservedLink":
        if (
            self.endpoint_a.device.casefold() == self.endpoint_b.device.casefold()
            and self.endpoint_a.interface.casefold() == self.endpoint_b.interface.casefold()
        ):
            raise ValueError("link endpoints must differ")
        return self


class NeighborClaim(BaseModel):
    """One-sided raw LLDP/CDP claim, retained even if it cannot be reconciled."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    local: InterfaceRef
    remote_device: str = Field(min_length=1)
    remote_interface: str | None = None
    protocol: Literal["lldp", "cdp"]
    evidence: list[EvidenceRef] = Field(min_length=1)


class ObservedMacEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    device: str = Field(min_length=1)
    vlan_id: int = Field(ge=1, le=4094)
    mac_address: str = Field(pattern=r"(?i)^(?:[0-9a-f]{2}[:-]){5}[0-9a-f]{2}$")
    interface: str = Field(min_length=1)
    evidence: list[EvidenceRef] = Field(min_length=1)


class ObservedArpEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    device: str = Field(min_length=1)
    address: IPAddressValue
    mac_address: str = Field(pattern=r"(?i)^(?:[0-9a-f]{2}[:-]){5}[0-9a-f]{2}$")
    interface: str | None = None
    evidence: list[EvidenceRef] = Field(min_length=1)


class ObservedOspfNeighbor(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    device: str = Field(min_length=1)
    interface: str = Field(min_length=1)
    neighbor_router_id: IPv4Address
    state: Literal[
        "down", "init", "2-way", "exstart", "exchange", "loading", "full", "unknown"
    ]
    evidence: list[EvidenceRef] = Field(min_length=1)


class ObservedVlan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    device: str = Field(min_length=1)
    vlan_id: int = Field(ge=1, le=4094)
    name: str | None = None
    prefixes: list[IPNetworkValue] = Field(default_factory=list)
    member_interfaces: list[str] = Field(default_factory=list)
    evidence: list[EvidenceRef] = Field(min_length=1)


class ObservedRoute(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    device: str = Field(min_length=1)
    prefix: IPNetworkValue
    protocol: Literal["connected", "static", "ospf", "bgp", "eigrp", "unknown"]
    next_hop: IPAddressValue | None = None
    outgoing_interface: str | None = None
    evidence: list[EvidenceRef] = Field(min_length=1)


class ObservedGatewayGroup(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    device: str = Field(min_length=1)
    protocol: Literal["hsrp", "vrrp"]
    group_id: int = Field(ge=0, le=4095)
    virtual_address: IPAddressValue
    state: Literal["active", "standby", "master", "backup", "unknown"]
    evidence: list[EvidenceRef] = Field(min_length=1)


class ObservedNetwork(BaseModel):
    """Version 1 snapshot of observed facts; no inferred fact is silently authoritative."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["v1"] = "v1"
    network_id: str = Field(min_length=1)
    collected_at: datetime
    freshness: FreshnessPolicy
    sources: list[EvidenceSource] = Field(min_length=1)
    devices: list[ObservedDevice] = Field(min_length=1)
    neighbor_claims: list[NeighborClaim] = Field(default_factory=list)
    links: list[ObservedLink] = Field(default_factory=list)
    vlans: list[ObservedVlan] = Field(default_factory=list)
    mac_entries: list[ObservedMacEntry] = Field(default_factory=list)
    arp_entries: list[ObservedArpEntry] = Field(default_factory=list)
    routes: list[ObservedRoute] = Field(default_factory=list)
    ospf_neighbors: list[ObservedOspfNeighbor] = Field(default_factory=list)
    gateway_groups: list[ObservedGatewayGroup] = Field(default_factory=list)
    reconciliation_findings: list[Finding] = Field(default_factory=list)

    @field_validator("collected_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("snapshot timestamps must include a timezone")
        return value

    @model_validator(mode="after")
    def validate_references_and_identities(self) -> "ObservedNetwork":
        source_ids = [source.source_id for source in self.sources]
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("source_id values must be unique")
        source_id_set = set(source_ids)
        source_by_id = {source.source_id: source for source in self.sources}
        if any(source.collected_at > self.collected_at for source in self.sources):
            raise ValueError("source collection times cannot be later than the snapshot time")
        device_by_name = {device.name.casefold(): device for device in self.devices}
        if len(device_by_name) != len(self.devices):
            raise ValueError("device names must be unique, ignoring case")

        interface_keys: set[tuple[str, str]] = set()
        for device in self.devices:
            local_names = [interface.name.casefold() for interface in device.interfaces]
            if len(local_names) != len(set(local_names)):
                raise ValueError(f"interface names on {device.name!r} must be unique")
            interface_keys.update((device.name.casefold(), name) for name in local_names)

        def validate_evidence(
            refs: list[EvidenceRef],
            owner: str,
            allowed_devices: set[str] | None = None,
        ) -> None:
            for ref in refs:
                if ref.source_id not in source_id_set:
                    raise ValueError(f"{owner} refers to unknown evidence source {ref.source_id!r}")
                source = source_by_id[ref.source_id]
                if ref.observed_at > source.collected_at:
                    raise ValueError(f"{owner} evidence time is later than its source collection")
                if (
                    allowed_devices is not None
                    and source.device.casefold() not in allowed_devices
                ):
                    raise ValueError(f"{owner} evidence source device cannot observe this fact")

        for source in self.sources:
            if source.device.casefold() not in device_by_name:
                raise ValueError(f"evidence source {source.source_id!r} refers to unknown device")
        for device in self.devices:
            owner_devices = {device.name.casefold()}
            validate_evidence(device.evidence, f"device {device.name!r}", owner_devices)
            for interface in device.interfaces:
                validate_evidence(
                    interface.evidence,
                    f"interface {device.name}/{interface.name}",
                    owner_devices,
                )
        link_keys: set[tuple[tuple[str, str], tuple[str, str]]] = set()
        for link in self.links:
            for endpoint in (link.endpoint_a, link.endpoint_b):
                key = (endpoint.device.casefold(), endpoint.interface.casefold())
                if key not in interface_keys:
                    raise ValueError("link endpoint must reference a known device interface")
            endpoint_keys = sorted(
                (
                    (link.endpoint_a.device.casefold(), link.endpoint_a.interface.casefold()),
                    (link.endpoint_b.device.casefold(), link.endpoint_b.interface.casefold()),
                )
            )
            canonical_key = (endpoint_keys[0], endpoint_keys[1])
            if canonical_key in link_keys:
                raise ValueError("duplicate reconciled link between the same endpoints")
            link_keys.add(canonical_key)
            endpoint_devices = {
                link.endpoint_a.device.casefold(),
                link.endpoint_b.device.casefold(),
            }
            validate_evidence(link.evidence, "link", endpoint_devices)
            evidence_kinds = {
                source_by_id[ref.source_id].kind for ref in link.evidence
            }
            source_ids_for_link = {ref.source_id for ref in link.evidence}
            if link.basis == "direct" and not evidence_kinds.intersection({"lldp", "cdp"}):
                raise ValueError("direct links must cite LLDP or CDP evidence")
            if link.basis == "reconciled" and len(source_ids_for_link) < 2:
                raise ValueError("reconciled links must cite at least two independent sources")
        for claim in self.neighbor_claims:
            key = (claim.local.device.casefold(), claim.local.interface.casefold())
            if key not in interface_keys:
                raise ValueError("neighbor claim must reference a known local interface")
            validate_evidence(
                claim.evidence,
                "neighbor claim",
                {claim.local.device.casefold()},
            )
            expected_kind = claim.protocol
            if any(source_by_id[ref.source_id].kind != expected_kind for ref in claim.evidence):
                raise ValueError("neighbor claim evidence kind must match its LLDP/CDP protocol")
        vlan_keys: set[tuple[str, int]] = set()
        for vlan in self.vlans:
            vlan_device = device_by_name.get(vlan.device.casefold())
            if vlan_device is None:
                raise ValueError(f"VLAN {vlan.vlan_id} refers to an unknown device")
            vlan_key = (vlan.device.casefold(), vlan.vlan_id)
            if vlan_key in vlan_keys:
                raise ValueError("observed VLAN IDs must be unique per device")
            vlan_keys.add(vlan_key)
            interface_names = {
                interface.name.casefold() for interface in vlan_device.interfaces
            }
            if any(name.casefold() not in interface_names for name in vlan.member_interfaces):
                raise ValueError(f"VLAN {vlan.vlan_id} refers to an unknown member interface")
            validate_evidence(
                vlan.evidence,
                f"VLAN {vlan.vlan_id}",
                {vlan.device.casefold()},
            )
        for route in self.routes:
            if route.device.casefold() not in device_by_name:
                raise ValueError("route refers to an unknown device")
            validate_evidence(
                route.evidence,
                f"route {route.prefix}",
                {route.device.casefold()},
            )
        for mac_entry in self.mac_entries:
            mac_device = device_by_name.get(mac_entry.device.casefold())
            if mac_device is None:
                raise ValueError("MAC entry refers to an unknown device")
            interface_names = {
                interface.name.casefold() for interface in mac_device.interfaces
            }
            if mac_entry.interface.casefold() not in interface_names:
                raise ValueError("MAC entry refers to an unknown interface")
            validate_evidence(
                mac_entry.evidence,
                f"MAC entry {mac_entry.mac_address}",
                {mac_entry.device.casefold()},
            )
        for arp_entry in self.arp_entries:
            if arp_entry.device.casefold() not in device_by_name:
                raise ValueError("ARP entry refers to an unknown device")
            validate_evidence(
                arp_entry.evidence,
                f"ARP entry {arp_entry.address}",
                {arp_entry.device.casefold()},
            )
        for neighbor in self.ospf_neighbors:
            ospf_device = device_by_name.get(neighbor.device.casefold())
            if ospf_device is None:
                raise ValueError("OSPF neighbor refers to an unknown device")
            interface_names = {
                interface.name.casefold() for interface in ospf_device.interfaces
            }
            if neighbor.interface.casefold() not in interface_names:
                raise ValueError("OSPF neighbor refers to an unknown interface")
            validate_evidence(
                neighbor.evidence,
                f"OSPF neighbor {neighbor.neighbor_router_id}",
                {neighbor.device.casefold()},
            )
        for group in self.gateway_groups:
            if group.device.casefold() not in device_by_name:
                raise ValueError("gateway group refers to an unknown device")
            validate_evidence(
                group.evidence,
                f"gateway group {group.group_id}",
                {group.device.casefold()},
            )
        for finding in self.reconciliation_findings:
            if not finding.evidence_refs:
                raise ValueError("reconciliation findings must include evidence references")
            validate_evidence(finding.evidence_refs, f"finding {finding.rule_id}")
        return self
