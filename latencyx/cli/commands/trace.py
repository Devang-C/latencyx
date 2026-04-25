from typing import Annotated, Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.tree import Tree

from ..db import open_db
from ..formatters import dur_style, fmt_dur, span_type_style, status_style

console = Console()


def run(
    trace_id: Annotated[str, typer.Argument(help="Trace ID to render")],
    db: Annotated[
        str,
        typer.Option("--db", help="Path to SQLite database"),
    ] = "latencyx_traces.db",
) -> None:
    """Render a full trace as a tree of spans with durations."""
    with open_db(db) as database:
        spans = database.get_trace(trace_id)

    if not spans:
        console.print(f"[red]Trace not found:[/] {trace_id}")
        raise typer.Exit(1)

    span_ids = {row["span_id"] for row in spans}
    children: dict = {}
    for row in spans:
        pid = row["parent_span_id"]
        children.setdefault(pid, []).append(row)

    roots = [
        row
        for row in spans
        if row["parent_span_id"] is None or row["parent_span_id"] not in span_ids
    ]

    def _make_label(row: object, is_root: bool = False) -> Text:
        label = Text()
        st = row["span_type"] or "span"  # type: ignore[index]
        label.append(f"{st:<14}", style=span_type_style(st))
        label.append("  ")
        label.append(row["span_name"], style="bold" if is_root else "")  # type: ignore[index]
        label.append("  ")
        ms = row["duration_ms"]  # type: ignore[index]
        label.append(fmt_dur(ms), style=dur_style(ms))
        code: Optional[int] = row["status_code"]  # type: ignore[index]
        if code is not None:
            label.append("  ")
            label.append(str(code), style=status_style(code))
        err = row["error"]  # type: ignore[index]
        if err:
            label.append(f"  {str(err)[:50]}", style="red")
        return label

    def _add_children(node: Tree, span_id: Optional[str]) -> None:
        for child in children.get(span_id, []):
            branch = node.add(_make_label(child))
            _add_children(branch, child["span_id"])

    console.print()
    console.print(
        Panel(
            f"[bold cyan]{trace_id}[/]  ·  "
            f"[dim]{len(spans)} span{'s' if len(spans) != 1 else ''}[/]",
            title="[bold]Trace[/]",
            border_style="dim",
            expand=False,
            padding=(0, 1),
        )
    )
    console.print()

    for root in roots:
        tree = Tree(_make_label(root, is_root=True))
        _add_children(tree, root["span_id"])
        console.print(tree)

    console.print()
