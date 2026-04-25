import copy

import pytest


@pytest.fixture(autouse=True)
def reset_latencyx_state():
    """Reset all global LatencyX state between tests so they don't bleed into each other."""
    import latencyx.exporters as exporters_module
    from latencyx.config import config

    saved = copy.deepcopy(vars(config))

    yield

    for k, v in saved.items():
        setattr(config, k, v)

    # Close any SQLiteExporter connections before clearing to avoid ResourceWarnings
    for exp in exporters_module._exporters:
        if hasattr(exp, "close"):
            exp.close()
    exporters_module._exporters.clear()

    # Undo httpx monkey-patch if it was applied during the test
    try:
        import latencyx.instrumentors.http_client as hc

        if hc._original_httpx_request is not None:
            import httpx

            httpx.Client.request = hc._original_httpx_request
            hc._original_httpx_request = None
    except (ImportError, AttributeError):
        pass

    # Clear SQLAlchemy engine tracking so each test gets fresh instrumentation
    try:
        import latencyx.instrumentors.sqlalchemy as sa_instr

        sa_instr._instrumented_engines.clear()
    except (ImportError, AttributeError):
        pass
