from datetime import datetime

import pytest
from pydantic import ValidationError

from netops.ir.v1.findings import Finding


def test_shared_finding_model_keeps_current_fields_and_adds_metadata() -> None:
    finding = Finding(
        rule_id="IOS-TEST",
        severity="blocker",
        device="r1",
        evidence="SVI address is missing",
        remediation="Regenerate the config and review it.",
        confidence="high",
        freshness="fresh",
        observed_at=datetime.fromisoformat("2026-10-20T10:00:00+00:00"),
    )

    assert finding.schema_version == "v1"
    assert finding.confidence == "high"
    assert finding.model_dump(mode="json")["rule_id"] == "IOS-TEST"


def test_finding_requires_timezone_and_known_severity() -> None:
    with pytest.raises(ValidationError, match="timezone"):
        Finding(
            rule_id="IOS-TEST",
            severity="warn",
            device="r1",
            evidence="stale fact",
            observed_at=datetime(2026, 10, 20, 10, 0, 0),
        )
    with pytest.raises(ValidationError):
        Finding(rule_id="IOS-TEST", severity="apply", device="r1", evidence="bad severity")
