import re
import time
from datetime import datetime, timezone
from typing import Optional

import typer
from rich.text import Text


def fmt_dur(ms: float) -> str:
    if ms < 100:
        return f"{ms:.2f}ms"
    if ms < 1000:
        return f"{ms:.1f}ms"
    return f"{ms / 1000:.2f}s"


def dur_style(ms: float) -> str:
    if ms < 100:
        return "green"
    if ms < 500:
        return "yellow"
    return "red bold"


def rate_style(pct: float) -> str:
    if pct == 0.0:
        return "green"
    if pct < 5.0:
        return "yellow"
    return "red bold"


def status_style(code: Optional[int]) -> str:
    if code is None:
        return "dim"
    if code < 300:
        return "green"
    if code < 500:
        return "yellow"
    return "red bold"


def fmt_dur_cell(ms: Optional[float]) -> Text:
    if ms is None:
        return Text("—", style="dim")
    return Text(fmt_dur(ms), style=dur_style(ms))


def fmt_rate_cell(pct: float) -> Text:
    return Text(f"{pct:.1f}%", style=rate_style(pct))


def fmt_status_cell(code: Optional[int]) -> Text:
    if code is None:
        return Text("—", style="dim")
    return Text(str(code), style=status_style(code))


def percentile(sorted_vals: list, p: float) -> Optional[float]:
    if not sorted_vals:
        return None
    idx = int(len(sorted_vals) * p / 100)
    return float(sorted_vals[min(idx, len(sorted_vals) - 1)])


def parse_since(s: str) -> float:
    m = re.fullmatch(r"(\d+(?:\.\d+)?)(s|m|h|d)", s)
    if m:
        val, unit = float(m.group(1)), m.group(2)
        secs = {"s": 1.0, "m": 60.0, "h": 3600.0, "d": 86400.0}[unit]
        return time.time() - val * secs

    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except ValueError:
        pass

    raise typer.BadParameter(
        f"{s!r} — use '30m', '2h', '7d', or ISO 8601 (e.g. 2024-01-15T10:00:00)"
    )


def fmt_timestamp(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, tz=timezone.utc).strftime("%H:%M:%S")


def span_type_style(span_type: str) -> str:
    t = span_type.lower()
    if "http.server" in t:
        return "cyan"
    if "db" in t or "sql" in t or "query" in t:
        return "yellow"
    if "http.client" in t:
        return "blue"
    return "white"
