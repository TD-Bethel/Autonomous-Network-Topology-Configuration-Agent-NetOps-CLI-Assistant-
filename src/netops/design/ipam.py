"""Stable IPv4 VLAN allocation with explicitly reserved growth headroom."""

from dataclasses import asdict, dataclass
from ipaddress import IPv4Address, IPv4Network
from math import ceil

from netops.ir.v1.intent import NetworkIntent


@dataclass(frozen=True, slots=True)
class VlanDesign:
    site: str
    vlan_id: int
    name: str
    purpose: str
    prefix: str
    gateway: str
    hosts_required: int
    headroom_hosts: int
    dhcp_enabled: bool
    dhcp_dns_server: str | None


@dataclass(frozen=True, slots=True)
class SiteDesign:
    name: str
    router_id: str


@dataclass(frozen=True, slots=True)
class P2PDesign:
    site: str
    interface: str
    peer: str
    local_address: str
    peer_address: str


@dataclass(frozen=True, slots=True)
class NetworkDesign:
    schema_version: str
    supernet: str
    loopback_supernet: str
    ospf_process_id: int
    ospf_area: int
    sites: tuple[SiteDesign, ...]
    p2p_links: tuple[P2PDesign, ...]
    vlans: tuple[VlanDesign, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "supernet": self.supernet,
            "loopback_supernet": self.loopback_supernet,
            "ospf_process_id": self.ospf_process_id,
            "ospf_area": self.ospf_area,
            "sites": [asdict(site) for site in self.sites],
            "p2p_links": [asdict(link) for link in self.p2p_links],
            "vlans": [asdict(vlan) for vlan in self.vlans],
        }


def _required_prefixlen(host_count: int) -> int:
    """Return a conventional VLAN prefix length with network/broadcast reserved."""
    if host_count > (1 << 32) - 3:
        raise ValueError("requested VLAN capacity exceeds IPv4 address space")
    address_count = max(4, host_count + 2)
    block_size = 1 << (address_count - 1).bit_length()
    return 32 - (block_size.bit_length() - 1)


def _align(address: int, block_size: int) -> int:
    return ((address + block_size - 1) // block_size) * block_size


def design_network(intent: NetworkIntent) -> NetworkDesign:
    """Allocate each VLAN from the supernet in a stable, largest-first order.

    Each VLAN reserves its requested hosts, ceil(requested * growth_pct / 100)
    headroom hosts, and one gateway address. The network and broadcast addresses
    are also reserved. Any duplicate identity or capacity failure is an error.
    """
    sites_by_name = sorted(intent.sites, key=lambda site: site.name.casefold())
    site_names = [site.name.casefold() for site in sites_by_name]
    if len(site_names) != len(set(site_names)):
        raise ValueError("site names must be unique, ignoring case")

    requests: list[tuple[str, str, str, int, int, int, bool, str | None]] = []
    seen_vlans: set[tuple[str, str]] = set()
    for site in sites_by_name:
        for vlan in site.vlans:
            key = (site.name.casefold(), vlan.name.casefold())
            if key in seen_vlans:
                raise ValueError(f"duplicate VLAN name {vlan.name!r} at site {site.name!r}")
            seen_vlans.add(key)
            headroom = ceil(vlan.hosts_required * vlan.growth_pct / 100)
            usable_required = vlan.hosts_required + headroom + 1
            prefixlen = _required_prefixlen(usable_required)
            requests.append(
                (
                    site.name,
                    vlan.name,
                    vlan.purpose,
                    vlan.hosts_required,
                    headroom,
                    prefixlen,
                    vlan.dhcp_enabled,
                    str(vlan.dhcp_dns_server) if vlan.dhcp_dns_server else None,
                )
            )

    requests.sort(key=lambda row: (row[5], row[0].casefold(), row[1].casefold()))
    network = intent.supernet
    cursor = int(network.network_address)
    end = int(network.broadcast_address) + 1
    allocated: list[tuple[str, str, str, int, int, IPv4Network, bool, str | None]] = []

    for (
        site_name,
        name,
        purpose,
        hosts,
        headroom,
        prefixlen,
        dhcp_enabled,
        dhcp_dns_server,
    ) in requests:
        block_size = 1 << (32 - prefixlen)
        start = _align(cursor, block_size)
        stop = start + block_size
        if start < int(network.network_address) or stop > end:
            raise ValueError(
                f"supernet {network} has insufficient space for {site_name}/{name} (/{prefixlen})"
            )
        prefix = IPv4Network((IPv4Address(start), prefixlen))
        allocated.append(
            (site_name, name, purpose, hosts, headroom, prefix, dhcp_enabled, dhcp_dns_server)
        )
        cursor = stop

    # IDs are assigned independently of subnet sizing so input order cannot affect them.
    ordered_vlans = sorted(
        ((site, vlan) for site in sites_by_name for vlan in site.vlans),
        key=lambda pair: (pair[0].name.casefold(), pair[1].name.casefold()),
    )
    available_ids = (*range(10, 1002), *range(1006, 4095))
    if len(ordered_vlans) > len(available_ids):
        raise ValueError("the design exceeds the available non-reserved VLAN ID range")
    ids = {
        (site.name.casefold(), vlan.name.casefold()): available_ids[index]
        for index, (site, vlan) in enumerate(ordered_vlans)
    }
    plans = tuple(
        VlanDesign(
            site=site,
            vlan_id=ids[(site.casefold(), name.casefold())],
            name=name,
            purpose=purpose,
            prefix=str(prefix),
            gateway=str(next(prefix.hosts())),
            hosts_required=hosts,
            headroom_hosts=headroom,
            dhcp_enabled=dhcp_enabled,
            dhcp_dns_server=dhcp_dns_server,
        )
        for site, name, purpose, hosts, headroom, prefix, dhcp_enabled, dhcp_dns_server in sorted(
            allocated, key=lambda row: (row[0].casefold(), row[1].casefold())
        )
    )
    loopback_network = intent.loopback_supernet
    site_designs = tuple(
        SiteDesign(
            name=site.name,
            router_id=str(IPv4Address(int(loopback_network.network_address) + index)),
        )
        for index, site in enumerate(sites_by_name)
    )
    p2p_links: list[P2PDesign] = []
    if intent.p2p_supernet is not None:
        p2p_network = intent.p2p_supernet
        link_requests = sorted(
            (
                (site.name, uplink.interface, uplink.peer)
                for site in sites_by_name
                for uplink in site.uplinks
            ),
            key=lambda row: (row[0].casefold(), row[1].casefold()),
        )
        for index, (site_name, interface, peer) in enumerate(link_requests):
            local = int(p2p_network.network_address) + index * 2
            p2p_links.append(
                P2PDesign(
                    site=site_name,
                    interface=interface,
                    peer=peer,
                    local_address=str(IPv4Address(local)),
                    peer_address=str(IPv4Address(local + 1)),
                )
            )
    return NetworkDesign(
        schema_version="v1",
        supernet=str(network),
        loopback_supernet=str(loopback_network),
        ospf_process_id=intent.ospf_process_id,
        ospf_area=intent.ospf_area,
        sites=site_designs,
        p2p_links=tuple(p2p_links),
        vlans=plans,
    )
