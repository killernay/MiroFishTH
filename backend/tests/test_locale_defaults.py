from app import create_app
from app.services.oasis_profile_generator import OasisProfileGenerator
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
    assert t("common.loading") == "กำลังโหลด..."


def test_legacy_chinese_worker_locale_is_normalized_to_english():
    set_locale("zh")

    assert get_locale() == "en"
    assert "English" in get_language_instruction()


def test_persona_fallbacks_follow_the_selected_output_language():
    set_locale("th")

    assert "เป็น" in OasisProfileGenerator._fallback_persona("Ada", "researcher")
    assert OasisProfileGenerator._default_country() == "ประเทศไทย"

    set_locale("en")
    assert OasisProfileGenerator._fallback_persona("Ada", "researcher") == (
        "Ada is a researcher participating in social discussions."
    )
    assert OasisProfileGenerator._default_country() == "Thailand"
