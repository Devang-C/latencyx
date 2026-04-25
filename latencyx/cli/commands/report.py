from typing import Annotated

import typer
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

from ..db import open_db
from ..formatters import (
    dur_style,
    fmt_dur,
    fmt_dur_cell,
    fmt_rate_cell,
    parse_since,
    percentile,
    rate_style,
)

console = Console()


def run(
    since: Annotated[
        str,
        typer.Option("--since", "-s", help="Time window (e.g. 1h, 30m, 7d)"),
    ] = "24h",
    db: Annotated[
        str,
        typer.Option("--db", help="Path to SQLite database"),
    ] = "latencyx_traces.db",
    limit: Annotated[
        int,
        typer.Option("--limit", help="Max items per section"),
    ] = 5,
) -> None:
    """Overview of request volume, error rate, slow endpoints, and recent errors."""
    since_epoch = parse_since(since)

    with open_db(db) as database:
        stats = database.get_global_stats(since_epoch)
        all_endpoints = database.get_endpoints(since_epoch)
        endpoints = sorted(all_endpoints, key=lambda e: e["p95"] or 0, reverse=True)[:limit]
        error_rows = database.get_errors(since_epoch, limit=limit)

    total = stats["total"]
    err_count = stats["errors"]
    durations = stats["durations"]
    error_rate = err_count / total * 100 if total > 0 else 0.0

    p50 = percentile(durations, 50) or 0.0
    p95 = percentile(durations, 95) or 0.0
    p99 = percentile(durations, 99) or 0.0

    if total == 0:
        summary: Text = Text("No data found for this time window.", style="dim")
    else:
        summary = Text()
        summary.append(f"{total:,}", style="bold white")
        summary.append(" requests  ·  ")
        summary.append(f"{err_count} errors ({error_rate:.1f}%)", style=rate_style(error_rate))
        summary.append("  ·  p50 ")
        summary.append(fmt_dur(p50), style=dur_style(p50))
        summary.append("  p95 ")
        summary.append(fmt_dur(p95), style=dur_style(p95))
        summary.append("  p99 ")
        summary.append(fmt_dur(p99), style=dur_style(p99))

    console.print(Panel(summary, title=f"[bold]LatencyX Report[/] · last {since}", padding=(0, 1)))
    console.print()

    # ── Slow endpoints ──────────────────────────────────────────────────────────
    console.print(Rule("[bold]Slow Endpoints[/]", style="dim"))
    console.print()

    if not endpoints:
        console.print("  [dim]No endpoint data.[/]\n")
    else:
        ep_table = Table(
            box=box.SIMPLE_HEAD,
            header_style="bold",
            show_edge=False,
            padding=(0, 1),
        )
        ep_table.add_column("Endpoint", style="cyan", no_wrap=True, min_width=32)
        ep_table.add_column("Requests", justify="right")
        ep_table.add_column("p50", justify="right", min_width=8)
        ep_table.add_column("p95", justify="right", min_width=8)
        ep_table.add_column("Error Rate", justify="right", min_width=10)

        for ep in endpoints:
            ep_table.add_row(
                ep["name"],
                str(ep["count"]),
                fmt_dur_cell(ep["p50"]),
                fmt_dur_cell(ep["p95"]),
                fmt_rate_cell(ep["error_rate"]),
            )
        console.print(ep_table)
        console.print()

    # ── Recent errors ───────────────────────────────────────────────────────────
    console.print(Rule("[bold]Recent Errors[/]", style="dim"))
    console.print()

    if not error_rows:
        console.print("  [dim][green]No errors.[/][/]\n")
    else:
        err_table = Table(
            box=box.SIMPLE_HEAD,
            header_style="bold",
            show_edge=False,
            padding=(0, 1),
        )
        err_table.add_column("Endpoint", style="cyan", no_wrap=True, min_width=28)
        err_table.add_column("Error", min_width=42)
        err_table.add_column("Count", justify="right", min_width=6)

        for row in error_rows:
            count = row["count"]
            count_style = "red bold" if count >= 10 else ("yellow" if count >= 3 else "white")
            err_table.add_row(
                row["endpoint"] or "—",
                Text(str(row["error"])[:60], style="dim"),
                Text(str(count), style=count_style),
            )
        console.print(err_table)
        console.print()
