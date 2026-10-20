from ipaddress import IPv4Network

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from netops.design.ipam import design_network
from netops.ir.v1.intent import NetworkIntent, Site, Uplink, Vlan


def make_intent(host_counts: list[int], supernet: str = "10.0.0.0/16") -> NetworkIntent:
    return NetworkIntent(
        supernet=supernet,
        loopback_supernet="172.31.255.0/24",
        sites=[
            Site(
                name="site-a",
                vlans=[
                    Vlan(name=f"vlan-{index}", purpose="staff", hosts_required=count)
                    for index, count in enumerate(host_counts)
                ],
            )
        ],
    )


def test_allocations_are_stable_and_non_overlapping() -> None:
    intent = make_intent([30, 500, 80, 8])
    first = design_network(intent)
    second = design_network(intent)
    networks = [IPv4Network(vlan.prefix) for vlan in first.vlans]

    assert first == second
    assert len(networks) == len(set(networks))
    assert all(
        left.network_address >= right.broadcast_address
        or right.network_address >= left.broadcast_address
        for index, left in enumerate(networks)
        for right in networks[index + 1 :]
    )
    assert all(IPv4Network(first.supernet).supernet_of(network) for network in networks)


def test_growth_headroom_is_reserved() -> None:
    design = design_network(make_intent([100]))
    vlan = design.vlans[0]

    assert vlan.headroom_hosts == 30
    usable = IPv4Network(vlan.prefix).num_addresses - 2
    assert usable >= vlan.hosts_required + vlan.headroom_hosts + 1


def test_loopback_and_p2p_allocations_are_deterministic() -> None:
    intent = NetworkIntent(
        supernet="10.0.0.0/16",
        loopback_supernet="10.255.0.0/24",
        p2p_supernet="192.0.2.0/24",
        sites=[
            Site(
                name="campus",
                vlans=[Vlan(name="users", purpose="staff", hosts_required=30)],
                uplinks=[Uplink(interface="GigabitEthernet1/0/1", peer="core01")],
            )
        ],
    )

    design = design_network(intent)

    assert design.sites[0].router_id == "10.255.0.0"
    assert design.p2p_links[0].local_address == "192.0.2.0"
    assert design.p2p_links[0].peer_address == "192.0.2.1"
    assert design == design_network(intent)


def test_duplicate_names_and_insufficient_space_fail_closed() -> None:
    duplicate = NetworkIntent(
        supernet="10.0.0.0/24",
        loopback_supernet="10.255.0.0/24",
        sites=[Site(name="a", vlans=[
            Vlan(name="users", purpose="staff", hosts_required=10),
            Vlan(name="users", purpose="guest", hosts_required=20),
        ])],
    )
    with pytest.raises(ValueError, match="duplicate VLAN"):
        design_network(duplicate)

    with pytest.raises(ValueError, match="insufficient space"):
        design_network(make_intent([2000], "192.0.2.0/30"))


@given(st.lists(st.integers(min_value=1, max_value=700), min_size=1, max_size=12))
@settings(max_examples=100, deadline=None)
def test_generated_allocations_never_overlap(host_counts: list[int]) -> None:
    design = design_network(make_intent(host_counts, "10.0.0.0/8"))
    networks = [IPv4Network(vlan.prefix) for vlan in design.vlans]

    assert all(not left.overlaps(right)
               for index, left in enumerate(networks) for right in networks[index + 1 :])
    assert all(IPv4Network(design.supernet).supernet_of(network) for network in networks)
    requested_by_name = {f"vlan-{index}": count for index, count in enumerate(host_counts)}
    for vlan in design.vlans:
        requested = requested_by_name[vlan.name]
        usable = IPv4Network(vlan.prefix).num_addresses - 2
        assert usable >= requested + vlan.headroom_hosts + 1
