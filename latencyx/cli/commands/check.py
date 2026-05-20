import time
from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.console import Console
from rich.rule import Rule
from rich.text import Text

from ..db import LatencyXDB

console = Console()
_err = Console(stderr=True)


def _fmt_bytes(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f} KB"
    return f"{n / (1024 * 1024):.1f} MB"


def _rel_time(epoch: float) -> str:
    diff = time.time() - epoch
    if diff < 5:
        return "just now"
    if diff < 60:
        return f"{int(diff)}s ago"
    if diff < 3600:
        return f"{int(diff / 60)}m ago"
    return f"{int(diff / 3600)}h ago"


def run(
    db: Annotated[
        str,
        typer.Option("--db", help="Path to SQLite database"),
    ] = "latencyx_traces.db",
) -> None:
    """Verify LatencyX is running and connected correctly."""
    console.print()
    db_path = Path(db)

    # ── Database file ────────────────────────────────────────────────────────

    console.print(Rule("[bold] Database [/]", style="dim", align="left"))

    if not db_path.exists():
        console.print(f"  [red]✗[/]  Not found: [bold]{db_path.resolve()}[/]\n")
        console.print("  [dim]Make sure:[/]")
        console.print("    1. The sqlite exporter is enabled (it is by default)")
        console.print("    2. Your app has called [bold]latencyx.init(app)[/]")
        console.print("    3. At least one request has been handled")
        console.print("    4. Run [bold]latencyx check[/] from your app's working directory")
        console.print()
        raise typer.Exit(1)

    size = db_path.stat().st_size
    console.print(f"  path    [dim]{db_path.resolve()}[/]  [dim]({_fmt_bytes(size)})[/]")

    # ── DB contents ──────────────────────────────────────────────────────────

    try:
        with LatencyXDB(str(db_path)) as database:
            info = database.get_db_info()
    except Exception as e:
        console.print(f"\n  [red]✗[/]  Could not read database: {e}\n")
        raise typer.Exit(1) from None

    schema = info["schema_version"]
    if schema is not None:
        console.print(f"  schema  [dim]v{schema}[/]")

    total = info["total_spans"]
    console.print(f"  spans   [bold]{total:,}[/] total")

    # ── Activity ─────────────────────────────────────────────────────────────

    console.print()
    console.print(Rule("[bold] Activity (last 1h) [/]", style="dim", align="left"))

    last_seen: Optional[float] = info["last_seen"]
    recent = info["recent_count"]
    errors = info["recent_errors"]
    services = info["services"]

    if last_seen is None:
        console.print("  [dim]No spans recorded yet.[/]")
        console.print()
        console.print("  [yellow]⚠[/]  Database is empty — no traces have been written.")
        console.print("     Is your app running and handling requests?\n")
        raise typer.Exit(0)

    console.print(f"  last seen   {_rel_time(last_seen)}")

    req_text = Text(f"  requests    {recent:,}")
    console.print(req_text)

    err_style = "red bold" if errors > 0 else "green"
    console.print(Text(f"  errors      {errors:,}", style=err_style if errors > 0 else ""))

    if services:
        console.print(f"  services    {', '.join(services)}")

    # ── Verdict ──────────────────────────────────────────────────────────────

    _ONE_HOUR_S = 3600.0
    _ONE_DAY_S = 86400.0
    console.print()
    age = time.time() - last_seen

    if age <= _ONE_HOUR_S and recent > 0:
        console.print("  [bold green]✓[/]  Healthy — connected and receiving traces.\n")
    elif age <= _ONE_DAY_S:
        console.print("  [yellow]⚠[/]  Stale — database found but no traces in the last hour.")
        console.print("     Is your app running and handling requests?\n")
    else:
        console.print("  [yellow]⚠[/]  Very stale — last trace was over a day ago.")
        console.print(f"     Last seen: {_rel_time(last_seen)}\n")
