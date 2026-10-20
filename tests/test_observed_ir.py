from pathlib import Path
from typing import Any

import pytest
import yaml

from netops.parse import load_observed_network

EXAMPLE = Path(__file__).parents[1] / "examples" / "observed-campus.yaml"


def read_example() -> dict[str, Any]:
    raw: Any = yaml.safe_load(EXAMPLE.read_text(encoding="utf-8"))
    assert isinstance(raw, dict)
    return raw


def test_observed_example_validates_with_sources_and_link_evidence() -> None:
    observed = load_observed_network(EXAMPLE)

    assert observed.schema_version == "v1"
    assert observed.network_id == "campus-example"
    assert len(observed.devices) == 2
    assert observed.links[0].basis == "direct"
    assert observed.links[0].confidence == "high"
    assert observed.ospf_neighbors[0].state == "full"


def test_unknown_evidence_source_is_rejected() -> None:
    raw = read_example()
    raw["links"][0]["evidence"][0]["source_id"] = "missing-source"

    with pytest.raises(ValueError, match="unknown evidence source"):
        from netops.ir.v1.observed import ObservedNetwork

        ObservedNetwork.model_validate(raw)


def test_unknown_link_endpoint_is_rejected() -> None:
    raw = read_example()
    raw["links"][0]["endpoint_b"]["interface"] = "GigabitEthernet9/9/9"

    with pytest.raises(ValueError, match="known device interface"):
        from netops.ir.v1.observed import ObservedNetwork

        ObservedNetwork.model_validate(raw)


def test_future_evidence_time_is_rejected() -> None:
    raw = read_example()
    raw["links"][0]["evidence"][0]["observed_at"] = "2026-10-20T10:02:00Z"

    with pytest.raises(ValueError, match="later than its source collection"):
        from netops.ir.v1.observed import ObservedNetwork

        ObservedNetwork.model_validate(raw)


def test_observed_model_rejects_unzoned_times() -> None:
    raw = read_example()
    raw["collected_at"] = "2026-10-20T10:05:00"

    with pytest.raises(ValueError, match="timezone"):
        from netops.ir.v1.observed import ObservedNetwork

        ObservedNetwork.model_validate(raw)


def test_direct_link_requires_neighbor_protocol_evidence() -> None:
    raw = read_example()
    raw["links"][0]["evidence"][0]["source_id"] = "sw1-interfaces"
    raw["links"][0]["evidence"][0]["observed_at"] = "2026-10-20T10:00:00Z"

    with pytest.raises(ValueError, match="direct links must cite LLDP or CDP"):
        from netops.ir.v1.observed import ObservedNetwork

        ObservedNetwork.model_validate(raw)


def test_reconciled_link_requires_independent_sources() -> None:
    raw = read_example()
    raw["links"][0]["basis"] = "reconciled"

    with pytest.raises(ValueError, match="at least two independent sources"):
        from netops.ir.v1.observed import ObservedNetwork

        ObservedNetwork.model_validate(raw)


def test_device_fact_rejects_evidence_from_an_unrelated_device() -> None:
    raw = read_example()
    raw["vlans"][0]["evidence"][0]["source_id"] = "r1-interfaces"
    raw["vlans"][0]["evidence"][0]["observed_at"] = "2026-10-20T10:00:00Z"

    with pytest.raises(ValueError, match="cannot observe this fact"):
        from netops.ir.v1.observed import ObservedNetwork

        ObservedNetwork.model_validate(raw)
