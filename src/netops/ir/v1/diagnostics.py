"""Declarative, non-executable diagnostic rule contracts."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from netops.ir.v1.findings import Confidence, FindingSeverity

FactKind = Literal[
    "ospf_neighbor",
    "routing_table",
    "traceroute",
    "reachability",
    "interface_counters",
    "interface_inventory",
    "acl_config",
    "telemetry_baseline",
    "observed_link",
]

DiagnosticSignature = Literal[
    "ospf_exstart",
    "route_missing_neighbor_up",
    "traceroute_blackhole",
    "one_way_reachability",
    "interface_error_rate_spike",
]

class EvidenceRequirement(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    fact_kind: FactKind
    max_age_seconds: int = Field(gt=0)
    minimum_sources: int = Field(default=1, ge=1)


class Predicate(BaseModel):
    """A bounded field comparison; no Python, shell, or device command expression."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    fact_kind: FactKind
    path: str = Field(pattern=r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)*$")
    operator: Literal["eq", "ne", "gt", "gte", "lt", "lte", "contains"]
    value: str | int | float | bool | None


class DiagnosticRule(BaseModel):
    """A hypothesis pattern; it cannot contain executable commands or device actions."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    rule_id: str = Field(min_length=1, pattern=r"^[A-Z0-9][A-Z0-9_.:-]*$")
    title: str = Field(min_length=1)
    signature: DiagnosticSignature
    severity: FindingSeverity
    confidence_cap: Confidence = "medium"
    hypothesis: str = Field(min_length=1)
    required_evidence: list[EvidenceRequirement] = Field(min_length=1)
    predicates: list[Predicate] = Field(min_length=1)
    minimum_topology_confidence: Confidence | None = None
    stale_evidence_behavior: Literal["warn", "block"] = "block"
    next_step: Literal[
        "collect_more_evidence",
        "compare_current_config",
        "validate_candidate_plan",
    ]
    references: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_signature_evidence(self) -> "DiagnosticRule":
        kinds = [item.fact_kind for item in self.required_evidence]
        if len(kinds) != len(set(kinds)):
            raise ValueError("required_evidence fact_kind values must be unique")
        if any(predicate.fact_kind not in kinds for predicate in self.predicates):
            raise ValueError("every predicate fact_kind must have a required_evidence entry")
        if self.minimum_topology_confidence is not None and "observed_link" not in kinds:
            raise ValueError(
                "minimum_topology_confidence requires observed_link evidence"
            )
        return self


class DiagnosticRuleSet(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["v1"] = "v1"
    rules: list[DiagnosticRule] = Field(min_length=1)

    @model_validator(mode="after")
    def require_unique_rule_ids(self) -> "DiagnosticRuleSet":
        ids = [rule.rule_id for rule in self.rules]
        if len(ids) != len(set(ids)):
            raise ValueError("diagnostic rule IDs must be unique")
        return self
