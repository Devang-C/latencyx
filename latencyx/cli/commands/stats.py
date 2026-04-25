from typing import Annotated

import typer
from rich import box
from rich.console import Console
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

from ..db import open_db
from ..formatters import (
    dur_style,
    fmt_dur,
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
) -> None:
    """At-a-glance overview: request volume, error rate, latency, and highlights."""
    since_epoch = parse_since(since)

    with open_db(db) as database:
        stats = database.get_global_stats(since_epoch)
        all_endpoints = database.get_endpoints(since_epoch)
        endpoints = sorted(all_endpoints, key=lambda e: e["p95"] or 0, reverse=True)[:3]
        error_rows = database.get_errors(since_epoch, limit=3)

    total = stats["total"]

    if total == 0:
        console.print(f"\n[bold]LatencyX Stats[/]  [dim]·  last {since}[/]\n")
        console.print(
            "  [dim]No data found. Is your app running with the sqlite exporter enabled?[/]\n"
        )
        return

    durations = stats["durations"]
    errors = stats["errors"]
    error_rate = errors / total * 100

    p50 = percentile(durations, 50) or 0.0
    p95 = percentile(durations, 95) or 0.0
    p99 = percentile(durations, 99) or 0.0

    # ── Summary line ────────────────────────────────────────────────────────────

    console.print(f"\n[bold]LatencyX Stats[/]  [dim]·  last {since}[/]\n")

    summary = Text("  ")
    summary.append(f"{total:,}", style="bold white")
    summary.append(" requests  ·  ", style="dim")
    summary.append(f"{errors} errors ({error_rate:.1f}%)", style=rate_style(error_rate))
    summary.append("  ·  ", style="dim")
    summary.append("p50 ", style="dim")
    summary.append(fmt_dur(p50), style=dur_style(p50))
    summary.append("  p95 ", style="dim")
    summary.append(fmt_dur(p95), style=dur_style(p95))
    summary.append("  p99 ", style="dim")
    summary.append(fmt_dur(p99), style=dur_style(p99))
    console.print(summary)
    console.print()

    # ── Slowest endpoints ───────────────────────────────────────────────────────

    console.print(Rule("[bold] Slowest [/]", style="dim", align="left"))

    if endpoints:
        t = Table(box=box.SIMPLE, show_header=False, padding=(0, 1), pad_edge=True, show_edge=False)
        t.add_column(style="cyan", no_wrap=True, min_width=38)
        t.add_column(justify="right")
        for ep in endpoints:
            p95_val = ep["p95"] or 0.0
            p95_text = Text()
            p95_text.append("p95  ", style="dim")
            p95_text.append(fmt_dur(p95_val), style=dur_style(p95_val))
            t.add_row(ep["name"], p95_text)
        console.print(t)
    else:
        console.print("  [dim]no data[/]\n")

    # ── Recent errors ───────────────────────────────────────────────────────────

    console.print(Rule("[bold] Errors [/]", style="dim", align="left"))

    if error_rows:
        t = Table(box=box.SIMPLE, show_header=False, padding=(0, 1), pad_edge=True, show_edge=False)
        t.add_column(style="cyan", no_wrap=True, min_width=28)
        t.add_column(style="dim", min_width=36)
        t.add_column(justify="right")
        for row in error_rows:
            endpoint = (row["endpoint"] or "unknown")[:36]
            error_msg = str(row["error"] or "")[:42]
            count_text = Text(f"× {row['count']}", style="red bold")
            t.add_row(endpoint, error_msg, count_text)
        console.print(t)
    else:
        console.print("  [dim green]no errors[/]\n")

    console.print()
