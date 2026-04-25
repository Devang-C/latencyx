import json
import time
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.text import Text

from ..formatters import dur_style, fmt_dur, span_type_style, status_style

console = Console()

_COL_TYPE = 16
_COL_NAME = 38
_COL_DUR = 11
_COL_STATUS = 8
_COL_DETAILS = 40
_SEP_WIDTH = _COL_TYPE + _COL_NAME + _COL_DUR + _COL_STATUS + _COL_DETAILS + 14


def run(
    file: Annotated[
        Path,
        typer.Option("--file", "-f", help="Path to JSONL traces file"),
    ] = Path("latencyx_traces.jsonl"),
    format: Annotated[
        str,
        typer.Option("--format", help="Output format: table or compact"),
    ] = "table",
    no_follow: Annotated[
        bool,
        typer.Option("--no-follow", help="Print existing traces and exit (don't tail)"),
    ] = False,
) -> None:
    """Watch traces in real-time from the JSONL file."""
    if not file.exists():
        console.print(f"[red]Error:[/] File not found: [bold]{file}[/]")
        console.print(
            "  Make sure the [bold]json_file[/] exporter is enabled in your LatencyX config."
        )
        raise typer.Exit(1)

    console.print(f"[bold]LatencyX[/] · watching [cyan]{file}[/]  [dim](Ctrl+C to stop)[/]\n")

    if format == "table":
        _print_header()

    try:
        with open(file) as f:
            if not no_follow:
                f.seek(0, 2)

            while True:
                line = f.readline()
                if line:
                    try:
                        data = json.loads(line.strip())
                        if format == "table":
                            _print_table_row(data)
                        else:
                            _print_compact_row(data)
                    except json.JSONDecodeError:
                        pass
                else:
                    if no_follow:
                        break
                    time.sleep(0.1)

    except KeyboardInterrupt:
        console.print("\n[dim]Stopped.[/]")


def _print_header() -> None:
    sep = "─" * _SEP_WIDTH
    console.print(f"[dim]{sep}[/]")
    console.print(
        f"[bold dim]{'TYPE':<{_COL_TYPE}}[/] │ "
        f"[bold dim]{'NAME':<{_COL_NAME}}[/] │ "
        f"[bold dim]{'DURATION':>{_COL_DUR}}[/] │ "
        f"[bold dim]{'STATUS':>{_COL_STATUS}}[/] │ "
        f"[bold dim]{'DETAILS':<{_COL_DETAILS}}[/]"
    )
    console.print(f"[dim]{sep}[/]")


def _print_table_row(data: dict) -> None:
    span_type = data.get("span_type", "unknown")
    span_name = data.get("span_name", "unknown")
    duration_ms = float(data.get("duration_ms", 0))

    dur_str = fmt_dur(duration_ms)
    t_style = span_type_style(span_type)
    d_style = dur_style(duration_ms)

    if "status_code" in data:
        status_display = str(data["status_code"])
        s_style = status_style(data["status_code"])
    else:
        status_display = data.get("status", "—")
        s_style = "dim"

    if data.get("error"):
        s_style = "red bold"
        status_display = "ERROR"

    details_parts = []
    for field, label in [
        ("method", "method"),
        ("path", "path"),
        ("host", "host"),
        ("client", "client"),
        ("url", "url"),
    ]:
        val = data.get(field)
        if val and str(val) not in span_name:
            details_parts.append(f"{label}={val}")
    if data.get("error"):
        details_parts.append(f"error={str(data['error'])[:30]}")

    details_str = " ".join(details_parts)

    if len(span_type) > _COL_TYPE:
        span_type = span_type[: _COL_TYPE - 1] + "…"
    if len(span_name) > _COL_NAME:
        span_name = span_name[: _COL_NAME - 1] + "…"
    if len(details_str) > _COL_DETAILS:
        details_str = details_str[: _COL_DETAILS - 1] + "…"

    row = Text()
    row.append(f"{span_type:<{_COL_TYPE}}", style=t_style)
    row.append(" │ ")
    row.append(f"{span_name:<{_COL_NAME}}")
    row.append(" │ ")
    row.append(f"{dur_str:>{_COL_DUR}}", style=d_style)
    row.append(" │ ")
    row.append(f"{status_display:>{_COL_STATUS}}", style=s_style)
    row.append(" │ ")
    row.append(f"{details_str:<{_COL_DETAILS}}", style="dim")
    console.print(row)


def _print_compact_row(data: dict) -> None:
    span_type = data.get("span_type", "unknown")
    span_name = data.get("span_name", "unknown")
    duration_ms = float(data.get("duration_ms", 0))
    d_style = dur_style(duration_ms)

    row = Text()
    row.append(f"[{span_type}]", style="dim")
    row.append(f" {span_name} duration=")
    row.append(fmt_dur(duration_ms), style=d_style)

    if "status_code" in data:
        code = data["status_code"]
        row.append(" status=")
        row.append(str(code), style=status_style(code))
    if data.get("method") and str(data["method"]) not in span_name:
        row.append(f" method={data['method']}")
    if data.get("host"):
        row.append(f" host={data['host']}")
    if data.get("error"):
        row.append(f" error={data['error']}", style="red bold")

    console.print(row)
