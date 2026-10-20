# System architecture

NetOps is a deterministic compiler pipeline. The validated intent is the contract between layers; the language model is not part of the current runtime implementation and has no authority over design, verification, or deployment.

```mermaid
flowchart LR
    human[Engineer-authored intent YAML] --> parse[Boundary parser]
    schema[Versioned Pydantic v1 IR] --> parse
    parse --> validate[IR validation and ambiguity rejection]
    validate --> design[Pure deterministic design engine]
    design --> ipam[IPv4 VLAN VLSM and growth headroom]
    design --> ids[Loopback /32 and optional uplink /31]
    design --> routing[Single-site OSPF plan]
    design --> render[Renderers]
    render --> ios[IOS config via Jinja2]
    render --> topology[Mermaid topology Markdown]
    design --> json[Design JSON]
    ios --> localVerify[Offline semantic verifier]
    design --> localVerify
    localVerify --> findings[Typed findings; blockers fail closed]
    snapshot[User-supplied Batfish snapshot] --> bf[Optional Batfish adapter]
    bf --> findings
    json --> review[Human review]
    ios --> review
    topology --> review
    findings --> review
    review -. explicit human approval required; no apply command exists .-> deployment[Future change-management boundary]
    llm[Future isolated LLM adapter] -. candidate intent or explanation only .-> parse
    findings -. explanation only .-> llm
```

## Layer responsibilities

| Layer | Owns | Current implementation |
| --- | --- | --- |
| IR (`src/netops/ir/v1`) | Versioned declarative input schema and validation | Pydantic models; IDs and subnets are not accepted from intent |
| Design (`src/netops/design`) | Deterministic allocation and planned facts | IPv4 VLAN blocks with headroom, stable VLAN IDs, `/32` router ID, optional `/31` uplinks |
| Render (`src/netops/render`, `src/netops/templates`) | Text output from the design | IOS VLAN/SVI, DHCP, loopback, uplink, and OSPF config; Mermaid topology Markdown |
| Verify (`src/netops/verify.py`) | Offline checks with structured findings | Fail-closed checks for the generated IOS subset |
| Optional provider (`src/netops/verify_batfish.py`) | Batfish answer conversion | `undefinedReferences` only; requires optional PyBatfish and a running service |
| CLI (`src/netops/cli.py`) | Paths, flags, files, exit codes, presentation | `design`, `verify`, `verify-batfish`, and `schema` commands |

## Trust and authority boundaries

- Intent YAML is user-controlled input and is rejected if invalid or underspecified for the implemented model.
- Design functions are synchronous and deterministic. They do not access files, devices, networks, or an LLM.
- Templates consume the design result; they do not make design decisions.
- Offline verification covers only implemented IOS syntax and semantics. It is not proof of device behavior or production readiness.
- The Batfish command is opt-in. Failure to import/connect/query fails as a blocker; it cannot silently turn an unavailable check into a pass.
- No device credentials, live configuration access, or apply/deploy command exists in this phase.
- The future LLM edge is intentionally absent today. If added, it may suggest schema-valid intent or explain findings; the deterministic core remains the authority.

## Scope boundary

This is a single-campus, IOS-focused phase-one implementation. IPv6, multi-site routing, BGP, ACL policy, CIS scoring, full Batfish analysis, lab emulation, signed change plans, human approval workflow, and deployment are future work. The topology diagram shows planned design facts—not discovered devices, live links, or telemetry.
