"""Optional Batfish undefined-reference gate.

The adapter is isolated so core tests do not require PyBatfish or Docker.
"""

import json
from collections.abc import Mapping, Sequence
from typing import Any

from netops.verify import Finding


class BatfishUnavailableError(RuntimeError):
    """Raised when the optional Batfish verification cannot be completed."""


def findings_from_undefined_references(
    rows: Sequence[Mapping[str, object]], device: str = "batfish"
) -> list[Finding]:
    """Convert Batfish undefined-reference answer rows into blocker findings."""
    return [
        Finding(
            rule_id="BATFISH-UNDEFINED-REFERENCE",
            severity="blocker",
            device=device,
            evidence=json.dumps(dict(row), sort_keys=True, default=str),
            remediation=(
                "Define or remove the unresolved configuration reference, then rerun Batfish."
            ),
        )
        for row in rows
    ]


def run_batfish_undefined_reference_check(session: Any) -> list[Finding]:
    """Run Batfish's undefinedReferences question through a PyBatfish session.

    Any connection, snapshot, query, or answer-conversion error fails closed and
    is returned as a blocker finding rather than being mistaken for a clean run.
    """
    try:
        frame = session.q.undefinedReferences().answer().frame()
        records = frame.to_dict(orient="records")
        return findings_from_undefined_references(records)
    except Exception as exc:  # provider boundaries must preserve query failures
        raise BatfishUnavailableError(f"Batfish undefinedReferences failed: {exc}") from exc


def unavailable_finding(error: Exception, device: str = "batfish") -> Finding:
    return Finding(
        rule_id="BATFISH-CHECK-UNAVAILABLE",
        severity="blocker",
        device=device,
        evidence=str(error),
        remediation=(
            "Start the configured Batfish service, verify the snapshot, and rerun the check."
        ),
    )
