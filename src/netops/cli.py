"""Thin command-line adapter for the deterministic compiler."""

import importlib
import json
from pathlib import Path
from typing import Annotated, Any, cast

import typer
from rich.console import Console
from rich.table import Table

from netops.design.ipam import design_network
from netops.parse import load_intent
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


@app.command()
def schema(
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
) -> None:
    """Print or write the versioned intent JSON Schema."""
    from netops.ir.v1.intent import NetworkIntent

    serialized = json.dumps(NetworkIntent.model_json_schema(), indent=2) + "\n"
    if output is None:
        console.print(serialized, end="")
    else:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(serialized, encoding="utf-8")
        console.print(f"Wrote {output}")
