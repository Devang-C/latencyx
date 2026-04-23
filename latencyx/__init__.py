from .config import config
from .core import init, timed


def instrument_sqlalchemy(engine: object) -> None:
    """Attach LatencyX tracing to a SQLAlchemy Engine.

    Call this after latencyx.init() and after your engine is created.
    Respects config.instrument_sqlalchemy — does nothing when False.
    """
    from .config import config as _config

    if not _config.instrument_sqlalchemy:
        return
    try:
        from .instrumentors.sqlalchemy import instrument_sqlalchemy as _instrument

        _instrument(engine)
    except ImportError:
        pass


__all__ = ["init", "timed", "config", "instrument_sqlalchemy"]
