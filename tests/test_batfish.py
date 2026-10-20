import pytest

from netops.verify_batfish import (
    BatfishUnavailableError,
    run_batfish_undefined_reference_check,
)


class FakeFrame:
    def __init__(self, records: list[dict[str, object]]) -> None:
        self.records = records

    def to_dict(self, orient: str) -> list[dict[str, object]]:
        assert orient == "records"
        return self.records


class FakeAnswer:
    def __init__(self, records: list[dict[str, object]]) -> None:
        self.records = records

    def frame(self) -> FakeFrame:
        return FakeFrame(self.records)

    def answer(self) -> "FakeAnswer":
        return self


class FakeQuery:
    def __init__(self, records: list[dict[str, object]]) -> None:
        self.records = records

    def undefinedReferences(self) -> FakeAnswer:
        return FakeAnswer(self.records)


class FakeSession:
    def __init__(self, records: list[dict[str, object]]) -> None:
        self.q = FakeQuery(records)


class BrokenSession:
    @property
    def q(self) -> object:
        raise RuntimeError("connection refused")


def test_batfish_rows_become_blocker_findings() -> None:
    findings = run_batfish_undefined_reference_check(
        FakeSession([{"Structure_Type": "ACL", "Structure_Name": "MISSING"}])
    )

    assert len(findings) == 1
    assert findings[0].rule_id == "BATFISH-UNDEFINED-REFERENCE"
    assert findings[0].severity == "blocker"
    assert "MISSING" in findings[0].evidence


def test_batfish_query_failure_fails_closed() -> None:
    with pytest.raises(BatfishUnavailableError, match="connection refused"):
        run_batfish_undefined_reference_check(BrokenSession())