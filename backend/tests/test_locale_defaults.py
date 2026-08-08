from app import create_app
from app.utils.locale import get_language_instruction, get_locale, set_locale, t


def test_locale_defaults_to_english_when_request_language_is_missing_or_unsupported():
    app = create_app()

    with app.test_request_context("/"):
        assert get_locale() == "en"

    with app.test_request_context("/", headers={"Accept-Language": "zh"}):
        assert get_locale() == "en"


def test_thai_is_available_to_background_workers_without_chinese_fallback():
    set_locale("th")

    assert get_locale() == "th"
    instruction = get_language_instruction()
    assert "ภาษาไทย" in instruction
    assert not any("\u4e00" <= character <= "\u9fff" for character in instruction)
    assert t("common.loading") == "Loading..."


def test_legacy_chinese_worker_locale_is_normalized_to_english():
    set_locale("zh")

    assert get_locale() == "en"
    assert "English" in get_language_instruction()
