"""Local Mermaid topology view for a deterministic network design."""

from netops.design.ipam import NetworkDesign


def _label(value: str) -> str:
    """Escape text for Mermaid's quoted HTML-like node labels."""
    return (
        value.replace("&", "&amp;")
        .replace('"', "&quot;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def render_topology_markdown(design: NetworkDesign) -> str:
    """Render a Markdown Mermaid diagram of planned VLANs and local uplinks."""
    lines = [
        "# Generated topology",
        "",
        "Generated from the validated intent design. This is a design view, not live telemetry.",
        "",
        "```mermaid",
        "flowchart TB",
    ]

    for site_index, site in enumerate(design.sites):
        site_label = f'{_label(site.name)}<br/>Router ID: {_label(site.router_id)}'
        lines.append(f'    site{site_index}["{site_label}"]')

        vlans = [vlan for vlan in design.vlans if vlan.site.casefold() == site.name.casefold()]
        for vlan_index, vlan in enumerate(vlans):
            vlan_label = (
                f"VLAN {vlan.vlan_id}: {_label(vlan.name)}<br/>"
                f"{_label(vlan.prefix)} | gateway {_label(vlan.gateway)}<br/>"
                f"{vlan.hosts_required} hosts + {vlan.headroom_hosts} growth"
            )
            node_id = f"vlan{site_index}_{vlan_index}"
            lines.append(f'    {node_id}["{vlan_label}"]')
            lines.append(f"    site{site_index} --> {node_id}")

        links = [link for link in design.p2p_links if link.site.casefold() == site.name.casefold()]
        for link_index, link in enumerate(links):
            peer_id = f"peer{site_index}_{link_index}"
            peer_label = (
                f"Peer: {_label(link.peer)}<br/>Peer address: {_label(link.peer_address)}/31"
            )
            link_label = (
                f"{_label(link.interface)}<br/>{_label(link.local_address)}/31 - OSPF p2p"
            )
            lines.append(f'    {peer_id}["{peer_label}"]')
            lines.append(f"    site{site_index} <-->|{link_label}| {peer_id}")

    lines.extend(
        [
            "```",
            "",
            "> Uplink peer nodes show the planned peer address only; peer-side configuration "
            "and live state are not modeled.",
            "",
        ]
    )
    return "\n".join(lines)
