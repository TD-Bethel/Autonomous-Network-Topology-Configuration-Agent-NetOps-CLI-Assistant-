import pytest
from pydantic import ValidationError

from netops.ir.v1.intent import NetworkIntent


def test_intent_rejects_unassigned_vlan_or_subnet_fields() -> None:
    with pytest.raises(ValidationError):
        NetworkIntent.model_validate(
            {
                "supernet": "10.0.0.0/24",
                "loopback_supernet": "10.255.0.0/24",
                "sites": [
                    {
                        "name": "hq",
                        "vlans": [
                            {
                                "name": "users",
                                "purpose": "staff",
                                "hosts_required": 20,
                                "vlan_id": 123,
                            }
                        ],
                    }
                ],
            }
        )


def test_intent_rejects_invalid_networks() -> None:
    with pytest.raises(ValidationError):
        NetworkIntent.model_validate(
            {
                "supernet": "not-a-network",
                "loopback_supernet": "10.255.0.0/24",
                "sites": [{"name": "hq", "vlans": []}],
            }
        )
