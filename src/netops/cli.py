"""Thin command-line adapter for the deterministic compiler."""

import importlib
import json
from pathlib import Path
from typing import Annotated, Any, Literal, cast

import typer
from pydantic import BaseModel
from rich.console import Console
from rich.table import Table

from netops.design.ipam import design_network
from netops.parse import load_diagnostic_rules, load_intent, load_observed_network
from netops.render.ios import render_ios
from netops.render.topology import render_topology_markdown
from netops.verify import verify_ios
from netops.verify_batfish import (
    run_batfish_undefined_reference_check,
    unavailable_finding,
)

app = typer.Typer(help="Offline-first deterministic network intent compiler.")
console = Console()


@app.command()
def design(
    intent: Annotated[Path, typer.Argument(exists=True, dir_okay=False, readable=True)],
    output: Annotated[Path, typer.Option("--output", "-o")] = Path("build"),
) -> None:
    """Validate intent, allocate VLANs, and render IOS configuration offline."""
    try:
        parsed = load_intent(intent)
        planned = design_network(parsed)
        config = render_ios(planned)
    except (OSError, ValueError) as exc:
        console.print(f"[red]Design rejected:[/red] {exc}")
        raise typer.Exit(code=2) from exc

    output.mkdir(parents=True, exist_ok=True)
    topology = render_topology_markdown(planned)
    (output / "design.json").write_text(
        json.dumps(planned.to_dict(), indent=2) + "\n", encoding="utf-8"
    )
    (output / "ios.cfg").write_text(config, encoding="utf-8")
    (output / "topology.md").write_text(topology, encoding="utf-8")
    console.print(
        f"Wrote {output / 'design.json'}, {output / 'ios.cfg'}, and {output / 'topology.md'}"
    )


@app.command()
def verify(
    intent: Annotated[Path, typer.Argument(exists=True, dir_okay=False, readable=True)],
    config: Annotated[Path, typer.Argument(exists=True, dir_okay=False, readable=True)],
) -> None:
    """Run offline semantic checks; any blocker exits nonzero."""
    try:
        design_result = design_network(load_intent(intent))
        findings = verify_ios(config.read_text(encoding="utf-8"), design_result)
    except (OSError, ValueError) as exc:
        console.print(f"[red]Verification unavailable:[/red] {exc}")
        raise typer.Exit(code=2) from exc

    if not findings:
        console.print("[green]PASS[/green] No blocker findings in the supported IOS subset.")
        return

    table = Table("Rule", "Severity", "Evidence", "Remediation")
    for finding in findings:
        table.add_row(
            finding.rule_id,
            finding.severity,
            finding.evidence,
            finding.remediation or "—",
        )
    console.print(table)
    raise typer.Exit(code=1)


@app.command("verify-batfish")
def verify_batfish(
    snapshot: Annotated[Path, typer.Argument(exists=True, file_okay=False, readable=True)],
    network: Annotated[str, typer.Option("--network")],
    host: Annotated[str, typer.Option("--host")] = "localhost",
) -> None:
    """Run the optional Batfish undefined-reference gate on a snapshot directory."""
    try:
        batfish_session = importlib.import_module("pybatfish.client.session")
        session_class = cast(Any, batfish_session).Session

        session = session_class(host=host)
        snapshot_name = f"netops-{snapshot.resolve().name}"
        session.set_network(network)
        session.init_snapshot(str(snapshot.resolve()), name=snapshot_name, overwrite=True)
        findings = run_batfish_undefined_reference_check(session)
    except Exception as exc:
        findings = [unavailable_finding(exc)]

    if not findings:
        console.print("[green]PASS[/green] Batfish reports no undefined references.")
        return

    table = Table("Rule", "Severity", "Device", "Evidence", "Remediation")
    for finding in findings:
        table.add_row(
            finding.rule_id,
            finding.severity,
            finding.device,
            finding.evidence,
            finding.remediation or "—",
        )
    console.print(table)
    raise typer.Exit(code=1)


@app.command("validate-observed")
def validate_observed(
    snapshot: Annotated[Path, typer.Argument(exists=True, dir_okay=False, readable=True)],
) -> None:
    """Validate an observed-network v1 snapshot and its provenance references."""
    try:
        observed = load_observed_network(snapshot)
    except (OSError, ValueError) as exc:
        console.print(f"[red]Observed snapshot rejected:[/red] {exc}")
        raise typer.Exit(code=2) from exc
    console.print(
        f"Valid observed network {observed.network_id}: {len(observed.devices)} devices, "
        f"{len(observed.links)} reconciled links, {len(observed.sources)} evidence sources."
    )


@app.command("validate-rules")
def validate_rules(
    rules_path: Annotated[Path, typer.Argument(exists=True, dir_okay=False, readable=True)],
) -> None:
    """Validate data-only diagnostic rules; this command does not execute them."""
    try:
        rules = load_diagnostic_rules(rules_path)
    except (OSError, ValueError) as exc:
        console.print(f"[red]Diagnostic rules rejected:[/red] {exc}")
        raise typer.Exit(code=2) from exc
    console.print(f"Valid diagnostic rule set: {len(rules.rules)} rules.")


@app.command()
def schema(
    kind: Annotated[
        Literal["intent", "observed", "finding", "diagnostic"], typer.Option("--kind")
    ] = "intent",
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
) -> None:
    """Print or write a versioned intent, observation, finding, or rule-set schema."""
    from netops.ir.v1.diagnostics import DiagnosticRuleSet
    from netops.ir.v1.findings import Finding
    from netops.ir.v1.intent import NetworkIntent
    from netops.ir.v1.observed import ObservedNetwork

    schema_models: dict[str, type[BaseModel]] = {
        "intent": NetworkIntent,
        "observed": ObservedNetwork,
        "finding": Finding,
        "diagnostic": DiagnosticRuleSet,
    }
    serialized = json.dumps(schema_models[kind].model_json_schema(), indent=2) + "\n"
    if output is None:
        console.print(serialized, end="")
    else:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(serialized, encoding="utf-8")
        console.print(f"Wrote {output}")
