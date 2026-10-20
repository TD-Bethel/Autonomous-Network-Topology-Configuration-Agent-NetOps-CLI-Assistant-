"""Input loading at the CLI boundary."""

from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from netops.ir.v1.intent import NetworkIntent


def load_intent(path: Path) -> NetworkIntent:
    """Load and validate a YAML intent document."""
    raw: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("intent document must contain a YAML mapping")
    try:
        return NetworkIntent.model_validate(raw)
    except ValidationError as exc:
        raise ValueError(f"invalid v1 intent:\n{exc}") from exc
