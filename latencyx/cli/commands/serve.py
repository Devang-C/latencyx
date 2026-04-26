import webbrowser
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

console = Console()


def run(
    db: Annotated[
        str,
        typer.Option("--db", help="Path to SQLite database"),
    ] = "latencyx_traces.db",
    port: Annotated[
        int,
        typer.Option("--port", help="Port to listen on"),
    ] = 4321,
    no_open: Annotated[
        bool,
        typer.Option("--no-open", help="Don't open browser automatically"),
    ] = False,
) -> None:
    """Start the LatencyX web UI and serve it in your browser."""
    try:
        import uvicorn
    except ImportError:
        console.print("[red]Error:[/] uvicorn is required to run the UI.")
        console.print("  Install it with: [bold]pip install latencyx\\[serve][/]")
        raise typer.Exit(1) from None

    try:
        from latencyx.serve import create_app
    except ImportError as e:
        console.print(f"[red]Error:[/] Could not load serve module: {e}")
        raise typer.Exit(1) from None

    db_path = Path(db)
    if not db_path.exists():
        console.print(f"[yellow]Warning:[/] Database not found: [bold]{db}[/]")
        console.print("  The UI will show an empty state until your app writes traces.")

    url = f"http://localhost:{port}"
    console.print(f"\n  [bold]→[/] LatencyX UI running at [bold cyan]{url}[/]")
    console.print(f"  [dim]database: {db_path.resolve()}[/]")
    console.print("  [dim]press Ctrl+C to stop[/]\n")

    if not no_open:
        import threading

        threading.Timer(0.8, lambda: webbrowser.open(url)).start()

    try:
        app = create_app(str(db_path.resolve()))
        uvicorn.run(app, host="0.0.0.0", port=port, log_level="error")
    except OSError as e:
        if "address already in use" in str(e).lower():
            console.print(f"\n[red]Error:[/] Port {port} is already in use.")
            console.print(f"  Try: [bold]latencyx serve --port {port + 1}[/]")
        else:
            console.print(f"\n[red]Error:[/] {e}")
        raise typer.Exit(1) from None
    except KeyboardInterrupt:
        console.print("\n[dim]Stopped.[/]")
