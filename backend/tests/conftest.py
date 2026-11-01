import pytest

from app.utils import zep


@pytest.fixture(autouse=True)
def _isolate_zep_read_rate_limit():
    """Start each test with an empty process-wide Zep read window.

    The Free-plan limiter is shared module state; without a reset, reads
    accumulated by earlier tests make later tests sleep for the real
    60-second window.
    """
    zep.clear_zep_read_rate_limit()
    yield
    zep.clear_zep_read_rate_limit()
