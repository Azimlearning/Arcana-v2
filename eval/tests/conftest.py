import pytest
import structlog


@pytest.fixture(autouse=True)
def reset_structlog():
    """The runner's configure_logging binds structlog to pytest's captured stdout, which is closed after the
    test; without this, a later test that logs fails with "I/O operation on closed file" depending on order."""
    yield
    structlog.reset_defaults()
