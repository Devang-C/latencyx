from importlib.metadata import PackageNotFoundError, version

from .config import config
from .core import init, timed

try:
    __version__ = version("latencyx")
except PackageNotFoundError:
    __version__ = "unknown"


def instrument_sqlalchemy(engine: object) -> None:
    """Attach LatencyX tracing to a SQLAlchemy Engine or AsyncEngine.

    Call this after latencyx.init() and after your engine is created.
    Respects config.instrument_sqlalchemy — does nothing when False.
    """
    if not config.instrument_sqlalchemy:
        return
    try:
        from .instrumentors.sqlalchemy import instrument_sqlalchemy as _instrument

        _instrument(engine)
    except ModuleNotFoundError:
        pass


__all__ = ["init", "timed", "config", "instrument_sqlalchemy", "__version__"]
