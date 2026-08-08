import logging

from app.utils.logger import LocaleSafeLogFilter, redact_han_text


def test_system_logs_redact_han_text_without_dropping_context():
    record = logging.LogRecord(
        name="test",
        level=logging.WARNING,
        pathname=__file__,
        lineno=1,
        msg="Interview failed: 模拟环境未运行 (%s)",
        args=("sim-test",),
        exc_info=None,
    )

    assert LocaleSafeLogFilter().filter(record) is True
    assert record.getMessage() == "Interview failed: [source text] (sim-test)"


def test_external_error_text_is_redacted_at_api_boundary():
    assert redact_han_text("模拟环境未运行: sim-test") == "[source text]: sim-test"
