from app.utils.logger import redact_han_text


def test_system_log_redaction_covers_common_cjk_scripts():
    raw = "中文日志 日本語 로그 — keep English and ไทย"
    rendered = redact_han_text(raw)
    assert "中文" not in rendered
    assert "日本語" not in rendered
    assert "로그" not in rendered
    assert "keep English" in rendered
    assert "ไทย" in rendered
