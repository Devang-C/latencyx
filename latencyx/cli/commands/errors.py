from typing import Annotated, Optional

import typer
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from ..db import open_db
from ..formatters import parse_since

console = Console()


def run(
    since: Annotated[
        str,
        typer.Option("--since", "-s", help="Time window (e.g. 1h, 30m, 7d)"),
    ] = "24h",
    path: Annotated[
        Optional[str],
        typer.Option("--path", "-p", help="Filter by endpoint (substring match)"),
    ] = None,
    limit: Annotated[
        int,
        typer.Option("--limit", help="Max error groups to show"),
    ] = 25,
    db: Annotated[
        str,
        typer.Option("--db", help="Path to SQLite database"),
    ] = "latencyx_traces.db",
) -> None:
    """Show recent errors grouped by endpoint and message, with counts."""
    since_epoch = parse_since(since)

    with open_db(db) as database:
        rows = database.get_errors(since_epoch, path=path, limit=limit)

    suffix = f" for [bold]{path}[/]" if path else ""
    if not rows:
        console.print(
            Panel(
                f"[green]No errors[/] found in the last {since}{suffix}",
                border_style="green",
                padding=(0, 1),
            )
        )
        return

    title = f"Errors · last {since}"
    if path:
        title += f"  ·  path~{path}"

    table = Table(
        box=box.ROUNDED,
        header_style="bold",
        title=title,
        title_style="bold red",
        title_justify="left",
    )
    table.add_column("Endpoint", style="cyan", min_width=28, no_wrap=True)
    table.add_column("Error", min_width=42)
    table.add_column("Count", justify="right", min_width=6)

    for row in rows:
        count = row["count"]
        count_style = "red bold" if count >= 10 else ("yellow" if count >= 3 else "white")
        table.add_row(
            row["endpoint"] or "—",
            Text(str(row["error"])[:80], style="dim"),
            Text(str(count), style=count_style),
        )

    console.print(table)
