from typing import Annotated, Optional

import typer
from rich import box
from rich.console import Console
from rich.table import Table

from ..db import open_db
from ..formatters import fmt_dur_cell, fmt_status_cell, fmt_timestamp, parse_since

console = Console()


def run(
    since: Annotated[
        str,
        typer.Option("--since", "-s", help="Start of time window (e.g. 1h, 30m, 7d)"),
    ] = "24h",
    until: Annotated[
        Optional[str],
        typer.Option("--until", help="End of time window (e.g. 30m, ISO 8601)"),
    ] = None,
    path: Annotated[
        Optional[str],
        typer.Option("--path", "-p", help="Filter by path (substring match)"),
    ] = None,
    status: Annotated[
        Optional[int],
        typer.Option("--status", help="Filter by HTTP status code"),
    ] = None,
    span_type: Annotated[
        Optional[str],
        typer.Option("--type", help="Filter by span type (e.g. http.server, db.query)"),
    ] = None,
    limit: Annotated[
        int,
        typer.Option("--limit", help="Max rows to show"),
    ] = 20,
    db: Annotated[
        str,
        typer.Option("--db", help="Path to SQLite database"),
    ] = "latencyx_traces.db",
) -> None:
    """Show the slowest requests, with optional filters."""
    since_epoch = parse_since(since)
    until_epoch = parse_since(until) if until else None

    with open_db(db) as database:
        rows = database.get_slowest(
            limit=limit,
            since=since_epoch,
            until=until_epoch,
            path=path,
            status_code=status,
            span_type=span_type,
        )

    if not rows:
        console.print(f"[dim]No traces found matching your filters for the last {since}.[/]")
        return

    title_parts = [f"Slowest Requests · last {since}"]
    if path:
        title_parts.append(f"path~{path}")
    if status:
        title_parts.append(f"status={status}")
    if span_type:
        title_parts.append(f"type={span_type}")

    table = Table(
        box=box.ROUNDED,
        header_style="bold",
        title="  ·  ".join(title_parts),
        title_style="bold",
        title_justify="left",
    )
    table.add_column("Time (UTC)", style="dim", min_width=10, no_wrap=True)
    table.add_column("Type", style="dim", min_width=12, no_wrap=True)
    table.add_column("Endpoint / Span", min_width=32, no_wrap=True)
    table.add_column("Duration", justify="right", min_width=9)
    table.add_column("Status", justify="right", min_width=7)
    table.add_column("Trace ID", style="dim cyan", min_width=32, no_wrap=True)

    for row in rows:
        table.add_row(
            fmt_timestamp(row["started_at"]),
            row["span_type"] or "—",
            row["span_name"],
            fmt_dur_cell(row["duration_ms"]),
            fmt_status_cell(row["status_code"]),
            row["trace_id"] or "—",
        )

    console.print(table)
