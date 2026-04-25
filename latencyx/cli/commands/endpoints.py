from typing import Annotated

import click
import typer
from rich import box
from rich.console import Console
from rich.table import Table
from rich.text import Text

from ..db import open_db
from ..formatters import fmt_dur_cell, fmt_rate_cell, parse_since, rate_style

console = Console()

_SORT_CHOICES = ["p95", "p50", "count", "errors"]


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
        typer.Option("--limit", help="Max endpoints to show"),
    ] = 25,
    sort: Annotated[
        str,
        typer.Option(
            "--sort",
            help="Sort by: p95, p50, count, errors",
            click_type=click.Choice(_SORT_CHOICES),
        ),
    ] = "p95",
) -> None:
    """List all endpoints with request count, p50/p95, and error rate."""
    since_epoch = parse_since(since)

    with open_db(db) as database:
        endpoints = database.get_endpoints(since_epoch)

    if not endpoints:
        console.print(f"[dim]No endpoint data found for the last {since}.[/]")
        return

    sort_key = {
        "p95": lambda e: e["p95"] or 0,
        "p50": lambda e: e["p50"] or 0,
        "count": lambda e: e["count"],
        "errors": lambda e: e["error_rate"],
    }[sort]
    endpoints = sorted(endpoints, key=sort_key, reverse=True)[:limit]

    table = Table(
        box=box.ROUNDED,
        header_style="bold",
        title=f"Endpoints · last {since}  [dim](sorted by {sort})[/]",
        title_style="bold",
        title_justify="left",
    )
    table.add_column("Endpoint", style="cyan", no_wrap=True, min_width=34)
    table.add_column("Requests", justify="right")
    table.add_column("p50", justify="right", min_width=8)
    table.add_column("p95", justify="right", min_width=8)
    table.add_column("Errors", justify="right")
    table.add_column("Error Rate", justify="right", min_width=10)

    for ep in endpoints:
        err_style = rate_style(ep["error_rate"])
        table.add_row(
            ep["name"],
            str(ep["count"]),
            fmt_dur_cell(ep["p50"]),
            fmt_dur_cell(ep["p95"]),
            Text(str(ep["errors"]), style=err_style),
            fmt_rate_cell(ep["error_rate"]),
        )

    console.print(table)
