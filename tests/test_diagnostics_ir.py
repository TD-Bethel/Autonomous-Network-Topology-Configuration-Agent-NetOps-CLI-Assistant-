import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
import yaml
from typer.testing import CliRunner

from netops.cli import app
from netops.ir.v1.diagnostics import DiagnosticRuleSet
from netops.ir.v1.findings import Finding
from netops.ir.v1.observed import ObservedNetwork
from netops.parse import load_diagnostic_rules

EXAMPLE = Path(__file__).parents[1] / "examples" / "diagnostic-rules-v1.yaml"


def read_example() -> dict[str, Any]:
    raw: Any = yaml.safe_load(EXAMPLE.read_text(encoding="utf-8"))
    assert isinstance(raw, dict)
    return raw


def test_diagnostic_rules_load_as_data_only_contracts() -> None:
    rules = load_diagnostic_rules(EXAMPLE)

    assert rules.schema_version == "v1"
    assert rules.rules[0].signature == "ospf_exstart"
    assert rules.rules[0].required_evidence[0].max_age_seconds == 300
    assert rules.rules[0].stale_evidence_behavior == "block"


def test_rule_rejects_predicate_without_freshness_requirement() -> None:
    raw = read_example()
    raw["rules"][0]["required_evidence"] = [
        raw["rules"][0]["required_evidence"][1]
    ]

    with pytest.raises(ValueError, match="required_evidence entry"):
        from netops.ir.v1.diagnostics import DiagnosticRuleSet

        DiagnosticRuleSet.model_validate(raw)


def test_rule_rejects_executable_action_fields() -> None:
    raw = read_example()
    raw["rules"][0]["command"] = "clear ip ospf process"

    with pytest.raises(ValueError, match="Extra inputs are not permitted"):
        from netops.ir.v1.diagnostics import DiagnosticRuleSet

        DiagnosticRuleSet.model_validate(raw)


def test_rule_set_rejects_duplicate_ids() -> None:
    raw = read_example()
    duplicate = deepcopy(raw["rules"][0])
    raw["rules"].append(duplicate)

    with pytest.raises(ValueError, match="must be unique"):
        from netops.ir.v1.diagnostics import DiagnosticRuleSet

        DiagnosticRuleSet.model_validate(raw)


@pytest.mark.parametrize(
    ("kind", "schema_name"),
    [
        ("observed", "observed-network-v1.schema.json"),
        ("finding", "finding-v1.schema.json"),
        ("diagnostic", "diagnostic-rules-v1.schema.json"),
    ],
)
def test_cli_exports_versioned_schema(kind: str, schema_name: str, tmp_path: Path) -> None:
    output = tmp_path / schema_name
    result = CliRunner().invoke(app, ["schema", "--kind", kind, "--output", str(output)])

    assert result.exit_code == 0, result.output
    assert '"$defs"' in output.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("model", "schema_name"),
    [
        (ObservedNetwork, "observed-network-v1.schema.json"),
        (Finding, "finding-v1.schema.json"),
        (DiagnosticRuleSet, "diagnostic-rules-v1.schema.json"),
    ],
)
def test_checked_in_schema_matches_pydantic_model(model: Any, schema_name: str) -> None:
    schema_path = Path(__file__).parents[1] / "schemas" / schema_name

    assert json.loads(schema_path.read_text(encoding="utf-8")) == model.model_json_schema()
