import typer

from .commands import endpoints, errors, report, slowest, stats, tail, trace

app = typer.Typer(
    name="latencyx",
    help="[bold]LatencyX[/] — latency tracking and observability",
    no_args_is_help=True,
    rich_markup_mode="rich",
    add_completion=False,
)

app.command("tail")(tail.run)
app.command("stats")(stats.run)
app.command("endpoints")(endpoints.run)
app.command("slowest")(slowest.run)
app.command("errors")(errors.run)
app.command("trace")(trace.run)
app.command("report")(report.run)


def main() -> None:
    app()
