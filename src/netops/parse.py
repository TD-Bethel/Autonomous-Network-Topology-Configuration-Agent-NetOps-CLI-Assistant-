"""Input loading at the CLI boundary."""

from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from netops.ir.v1.diagnostics import DiagnosticRuleSet
from netops.ir.v1.intent import NetworkIntent
from netops.ir.v1.observed import ObservedNetwork


def load_intent(path: Path) -> NetworkIntent:
    """Load and validate a YAML intent document."""
    raw: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("intent document must contain a YAML mapping")
    try:
        return NetworkIntent.model_validate(raw)
    except ValidationError as exc:
        raise ValueError(f"invalid v1 intent:\n{exc}") from exc


def load_observed_network(path: Path) -> ObservedNetwork:
    """Load a versioned, provenance-checked observed-network YAML snapshot."""
    raw: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("observed-network document must contain a YAML mapping")
    try:
        return ObservedNetwork.model_validate(raw)
    except ValidationError as exc:
        raise ValueError(f"invalid observed-network v1 document:\n{exc}") from exc


def load_diagnostic_rules(path: Path) -> DiagnosticRuleSet:
    """Load a versioned data-only diagnostic rule set."""
    raw: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("diagnostic-rules document must contain a YAML mapping")
    try:
        return DiagnosticRuleSet.model_validate(raw)
    except ValidationError as exc:
        raise ValueError(f"invalid diagnostic-rules v1 document:\n{exc}") from exc
