"""Fail-closed offline semantic checks for the generated IOS subset."""

import re
from ipaddress import IPv4Network

from netops.design.ipam import NetworkDesign
from netops.ir.v1.findings import Finding, FindingSeverity


def _make_finding(
    rule_id: str,
    severity: FindingSeverity,
    device: str,
    evidence: str,
    remediation: str,
) -> Finding:
    return Finding(
        rule_id=rule_id,
        severity=severity,
        device=device,
        evidence=evidence,
        remediation=remediation,
    )


def verify_ios(config: str, design: NetworkDesign, device: str = "offline") -> list[Finding]:
    """Check expected VLAN/SVI semantics and reject duplicate/unknown VLAN objects."""
    findings: list[Finding] = []
    stanzas = [
        stanza.strip()
        for stanza in re.split(r"(?m)^[ \t]*![ \t]*\r?$", config)
        if stanza.strip()
    ]
    vlan_ids = [
        int(match.group(1))
        for stanza in stanzas
        if (match := re.match(r"(?m)^vlan\s+(\d+)\s*$", stanza)) is not None
    ]
    svi_ids = [
        int(match.group(1))
        for stanza in stanzas
        if (match := re.match(r"(?m)^interface\s+Vlan(\d+)\s*$", stanza)) is not None
    ]

    for label, values in (("VLAN", vlan_ids), ("SVI", svi_ids)):
        duplicates = sorted({value for value in values if values.count(value) > 1})
        if duplicates:
            findings.append(
                _make_finding(
                    "IOS-DUPLICATE-OBJECT",
                    "blocker",
                    device,
                    f"duplicate {label} identifiers: {duplicates}",
                    f"Keep exactly one definition for each {label}.",
                )
            )

    expected_ids = {vlan.vlan_id for vlan in design.vlans}
    for unknown in sorted(set(vlan_ids + svi_ids) - expected_ids):
        findings.append(
            _make_finding(
                "IOS-UNEXPECTED-VLAN",
                "blocker",
                device,
                f"configuration contains unplanned VLAN/SVI {unknown}",
                "Update the intent or remove the unplanned object.",
            )
        )

    expected_pools = {
        f"{vlan.site}_{vlan.name}" for vlan in design.vlans if vlan.dhcp_enabled
    }
    actual_pools = {
        match.group(1)
        for stanza in stanzas
        if (match := re.match(r"(?m)^ip dhcp pool\s+(\S+)\s*$", stanza)) is not None
    }
    for unknown_pool in sorted(actual_pools - expected_pools):
        findings.append(
            _make_finding(
                "IOS-UNEXPECTED-DHCP-POOL",
                "blocker",
                device,
                f"configuration contains unplanned DHCP pool {unknown_pool}",
                "Update the intent or remove the unplanned pool.",
            )
        )

    for vlan in design.vlans:
        vlan_header = f"vlan {vlan.vlan_id}"
        svi_header = f"interface Vlan{vlan.vlan_id}"
        vlan_stanza = next((s for s in stanzas if s.splitlines()[0] == vlan_header), "")
        svi_stanza = next((s for s in stanzas if s.splitlines()[0] == svi_header), "")
        expected = (
            (bool(vlan_stanza), "VLAN definition"),
            (
                re.search(rf"(?m)^[ \t]*name[ \t]+{re.escape(vlan.name)}[ \t]*$", vlan_stanza)
                is not None,
                "VLAN name",
            ),
            (bool(svi_stanza), "SVI"),
            (
                re.search(
                    rf"(?m)^[ \t]*ip address[ \t]+{re.escape(vlan.gateway)}[ \t]+"
                    rf"{re.escape(str(IPv4Network(vlan.prefix).netmask))}[ \t]*$",
                    svi_stanza,
                )
                is not None,
                "SVI address",
            ),
            (
                re.search(
                    rf"(?m)^[ \t]*ip ospf[ \t]+{design.ospf_process_id}[ \t]+"
                    rf"area[ \t]+{design.ospf_area}[ \t]*$",
                    svi_stanza,
                )
                is not None,
                "SVI OSPF area",
            ),
            (re.search(r"(?m)^[ \t]*no shutdown[ \t]*$", svi_stanza) is not None, "enabled SVI"),
        )
        for found, label in expected:
            if not found:
                findings.append(
                    _make_finding(
                        "IOS-MISSING-EXPECTED-STATE",
                        "blocker",
                        device,
                        f"missing {label} for {vlan.site}/{vlan.name} (VLAN {vlan.vlan_id})",
                        "Regenerate from the validated design and review the resulting diff.",
                    )
                )

        if vlan.dhcp_enabled:
            pool_header = f"ip dhcp pool {vlan.site}_{vlan.name}"
            pool_stanza = next((s for s in stanzas if s.splitlines()[0] == pool_header), "")
            expected_dhcp: list[tuple[bool, str]] = [
                (
                    re.search(
                        rf"(?m)^[ \t]*network[ \t]+"
                        rf"{re.escape(str(IPv4Network(vlan.prefix).network_address))}"
                        rf"[ \t]+{re.escape(str(IPv4Network(vlan.prefix).netmask))}[ \t]*$",
                        pool_stanza,
                    )
                    is not None,
                    "DHCP network",
                ),
                (
                    re.search(
                        rf"(?m)^[ \t]*default-router[ \t]+{re.escape(vlan.gateway)}[ \t]*$",
                        pool_stanza,
                    )
                    is not None,
                    "DHCP default router",
                ),
            ]
            if vlan.dhcp_dns_server is not None:
                expected_dhcp.append(
                    (
                        re.search(
                            rf"(?m)^[ \t]*dns-server[ \t]+{re.escape(vlan.dhcp_dns_server)}[ \t]*$",
                            pool_stanza,
                        )
                        is not None,
                        "DHCP DNS server",
                    )
                )
            for found, label in [(bool(pool_stanza), "DHCP pool"), *expected_dhcp]:
                if not found:
                    findings.append(
                        _make_finding(
                            "IOS-MISSING-DHCP-STATE",
                            "blocker",
                            device,
                            f"missing {label} for {vlan.site}/{vlan.name}",
                            "Regenerate the pool from intent and review the resulting diff.",
                        )
                    )

    router_id = design.sites[0].router_id
    loopback_stanza = next(
        (s for s in stanzas if s.splitlines()[0] == "interface Loopback0"), ""
    )
    loopback_expectations = (
        re.search(
            rf"(?m)^[ \t]*ip address[ \t]+{re.escape(router_id)}[ \t]+255\.255\.255\.255$",
            loopback_stanza,
        )
        is not None,
        re.search(
            rf"(?m)^[ \t]*ip ospf[ \t]+{design.ospf_process_id}[ \t]+area[ \t]+{design.ospf_area}$",
            loopback_stanza,
        )
        is not None,
    )
    if not all(loopback_expectations):
        findings.append(
            _make_finding(
                "IOS-MISSING-LOOPBACK",
                "blocker",
                device,
                f"loopback router-ID {router_id}/32 is incomplete",
                "Render Loopback0 with the designed /32 and OSPF area.",
            )
        )

    ospf_header = f"router ospf {design.ospf_process_id}"
    ospf_stanza = next((s for s in stanzas if s.splitlines()[0] == ospf_header), "")
    if not ospf_stanza or not all(
        (
            re.search(rf"(?m)^[ \t]*router-id[ \t]+{re.escape(router_id)}[ \t]*$", ospf_stanza),
            re.search(r"(?m)^[ \t]*passive-interface default[ \t]*$", ospf_stanza),
        )
    ):
        findings.append(
            _make_finding(
                "IOS-MISSING-OSPF-BASELINE",
                "blocker",
                device,
                f"OSPF process {design.ospf_process_id} is missing router-ID or "
                "passive-interface default",
                "Regenerate the OSPF process from the validated design.",
            )
        )

    for link in design.p2p_links:
        link_stanza = next(
            (s for s in stanzas if s.splitlines()[0] == f"interface {link.interface}"), ""
        )
        link_patterns = (
            rf"(?m)^[ \t]*ip address[ \t]+{re.escape(link.local_address)}[ \t]+255\.255\.255\.254$",
            r"(?m)^[ \t]*ip ospf network point-to-point[ \t]*$",
            rf"(?m)^[ \t]*ip ospf[ \t]+{design.ospf_process_id}"
            rf"[ \t]+area[ \t]+{design.ospf_area}[ \t]*$",
            r"(?m)^[ \t]*no shutdown[ \t]*$",
        )
        if not all(re.search(pattern, link_stanza) for pattern in link_patterns):
            findings.append(
                _make_finding(
                    "IOS-MISSING-P2P-STATE",
                    "blocker",
                    device,
                    f"uplink {link.interface} to {link.peer} is not a complete "
                    "/31 OSPF point-to-point link",
                    "Regenerate the uplink from the allocated /31 and review it before use.",
                )
            )
        if not re.search(
            rf"(?m)^[ \t]*no passive-interface[ \t]+{re.escape(link.interface)}[ \t]*$",
            ospf_stanza,
        ):
            findings.append(
                _make_finding(
                    "IOS-MISSING-OSPF-NEIGHBOR-ENABLEMENT",
                    "blocker",
                    device,
                    f"OSPF uplink {link.interface} is not explicitly non-passive",
                    "Add no passive-interface for the designed uplink.",
                )
            )

    return findings


def findings_as_dicts(findings: list[Finding]) -> list[dict[str, object]]:
    return [finding.model_dump(mode="json") for finding in findings]
