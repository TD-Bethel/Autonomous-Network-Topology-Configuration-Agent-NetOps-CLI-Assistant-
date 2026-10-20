# NetOps CLI Assistant

An offline-first network intent compiler. The source of truth is a versioned, validated intent document; design and rendering are deterministic Python; verification fails closed. The LLM is deliberately not part of this MVP, and it must never author configuration or approve/apply a change.

## MVP scope

- Validate YAML intent against the Pydantic v2 IR.
- Allocate IPv4 VLAN subnets from a caller-supplied supernet, reserving configured growth plus one gateway address. Allocations are stable, aligned, and rejected if they do not fit.
- Allocate stable `/32` loopback router IDs and optional `/31` point-to-point links from disjoint pools.
- Render deterministic IOS VLAN/SVI, DHCP, loopback, point-to-point, and passive-by-default OSPF configuration for one campus site.
- Check rendered configuration against the design offline and return structured findings.
- Run an optional Batfish undefined-reference gate; Batfish is not part of the fast build.
- No live-device access, config push, credentials, or cloud LLM.

This phase-one slice does **not** yet implement IPv6, multi-site design, BGP, ACL policy, CIS baseline scoring, brownfield parsing, full Batfish semantic checks, Containerlab, signed change plans, or deployment. OSPF authentication, BFD, DHCP reservations/options, trunk/L2 design, redundancy, and peer-side uplink configuration are not generated yet. Do not treat a successful offline check as production approval.

## Quick start

Requires Python 3.12+ and `uv`.

```powershell
uv sync --extra dev
uv run pytest
uv run ruff check .
uv run mypy
uv run netops design examples/campus.yaml --output build
uv run netops verify examples/campus.yaml build/ios.cfg
```

`netops design` writes `design.json`, `ios.cfg`, and `topology.md` under the output directory. `netops verify` exits nonzero if any blocker finding is present. Nothing is deployed.

Open `build/topology.md` in VS Code and use **Markdown: Open Preview** (`Ctrl+Shift+V`) to see the Mermaid network diagram. The diagram and its source are local and static; they describe the planned design, not live network state.

See [System architecture](docs/architecture.md) for component boundaries and trust rules, and [Build, test, and visualize](docs/workflow.md) for the full input-to-output workflow and visualization notes.

To run the optional Batfish undefined-reference check, start a compatible Batfish service and install the extra with `uv sync --extra dev --extra batfish`, then run `uv run netops verify-batfish --network <network-name> <snapshot-directory>`. Missing PyBatfish, a failed query, or an unavailable snapshot fails closed. This one check is not the complete semantic/behavioral verification roadmap.

The brownfield contract drafts can be checked with `uv run netops validate-observed examples/observed-campus.yaml` and `uv run netops validate-rules examples/diagnostic-rules-v1.yaml`. These commands validate data only; discovery, reconciliation, stale-data evaluation, and diagnostic execution are not implemented. Generate their schemas with `uv run netops schema --kind observed`, `--kind finding`, or `--kind diagnostic`.

For the brownfield contract examples, see [`examples/observed-campus.yaml`](examples/observed-campus.yaml) and [`examples/diagnostic-rules-v1.yaml`](examples/diagnostic-rules-v1.yaml). Their generated schemas are in [`schemas/`](schemas/). `ObservedNetwork` preserves source references and timestamps; freshness policy is declared but not evaluated by a discovery or diagnosis engine yet.

## Intent

See [`examples/campus.yaml`](examples/campus.yaml). It intentionally contains no VLAN IDs or prefixes: those are derived by the design engine.

## Design guarantees

- Design results are sorted and deterministic for an identical intent and software version.
- Allocations never extend beyond the declared supernet and cannot overlap one another.
- Invalid or undersized designs fail rather than silently changing the request.
- Verification findings carry a rule identifier, severity, evidence, and remediation.
- The Batfish adapter currently runs only `undefinedReferences`; it does not imply OSPF/BGP compatibility or reachability checks.
- The CLI has no deployment command.
- Observed-network, Finding, and diagnostic rule-set contracts are versioned v1 schemas. Observed facts require source-linked evidence; consumers must still enforce the declared max-age policy before joining facts.

These guarantees are tested for the implemented IPv4 VLAN allocation path; they are not claims about unimplemented protocols or real-device behavior.

## Development

```powershell
uv sync --extra dev
uv run pytest
uv run ruff check .
uv run mypy
uv build
```

GitHub repository: [TD-Bethel/Autonomous-Network-Topology-Configuration-Agent-NetOps-CLI-Assistant-](https://github.com/TD-Bethel/Autonomous-Network-Topology-Configuration-Agent-NetOps-CLI-Assistant-). The local `main` branch tracks `origin/main`.
