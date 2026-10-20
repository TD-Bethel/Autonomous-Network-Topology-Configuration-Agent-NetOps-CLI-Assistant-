"""Timestamped evidence and source provenance shared by observed-network IR."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

EvidenceKind = Literal[
    "lldp",
    "cdp",
    "interface_inventory",
    "mac_fdb",
    "arp",
    "routing_table",
    "ospf_neighbor",
    "hsrp_vrrp",
    "config",
    "snmp",
    "netconf",
    "manual",
]


class EvidenceSource(BaseModel):
    """A source invocation or collection channel, never a credential/payload store."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: str = Field(min_length=1, pattern=r"^[A-Za-z][A-Za-z0-9_.:-]*$")
    kind: EvidenceKind
    device: str = Field(min_length=1)
    method: str = Field(min_length=1)
    collected_at: datetime

    @field_validator("collected_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("evidence timestamps must include a timezone")
        return value


class EvidenceRef(BaseModel):
    """A concise, redacted observation locator attached to a fact or finding."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: str = Field(min_length=1, pattern=r"^[A-Za-z][A-Za-z0-9_.:-]*$")
    observed_at: datetime
    locator: str = Field(min_length=1)
    summary: str = Field(min_length=1)

    @field_validator("observed_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("evidence timestamps must include a timezone")
        return value
