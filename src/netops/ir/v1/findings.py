"""Versioned shared finding contract for verification and future operations."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from netops.ir.v1.evidence import EvidenceRef

FindingSeverity = Literal["blocker", "warn", "info"]
Confidence = Literal["high", "medium", "low"]
Freshness = Literal["fresh", "stale", "unknown"]


class Finding(BaseModel):
    """A stable, provenance-capable observation or verification result."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["v1"] = "v1"
    rule_id: str = Field(min_length=1, pattern=r"^[A-Z0-9][A-Z0-9_.:-]*$")
    severity: FindingSeverity
    device: str = Field(min_length=1)
    evidence: str = Field(min_length=1)
    remediation: str | None = None
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    confidence: Confidence | None = None
    freshness: Freshness = "unknown"
    observed_at: datetime | None = None

    @field_validator("observed_at")
    @classmethod
    def require_timezone(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("finding timestamps must include a timezone")
        return value
