"""Language boundary for user-visible LLM output.

Quoted source evidence is deliberately excluded by its caller through
``evidence_paths``.  The validator never translates or mutates input values.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from typing import Any, TypeVar


_UNSUPPORTED_GENERATED_SCRIPT = re.compile(
    "["
    "\u0400-\u052f"  # Cyrillic
    "\u1100-\u11ff\u3130-\u318f\ua960-\ua97f\uac00-\ud7ff"  # Hangul
    "\u3040-\u30ff\u31f0-\u31ff"  # Hiragana and Katakana
    "\u3100-\u312f\u31a0-\u31bf"  # Bopomofo
    "\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff"  # Han
    "\U00020000-\U000323af\U0002f800-\U0002fa1f"  # Han extensions
    "]"
)
_CONTENT_LANGUAGE_ERRORS = {
    "en": "Generated content did not match the selected language. Please try again.",
    "th": "เนื้อหาที่สร้างไม่ตรงกับภาษาที่เลือก โปรดลองอีกครั้ง",
}
_RETRY_INSTRUCTIONS = {
    "en": (
        "Your previous output contained a script that is not allowed for this run. Regenerate "
        "all generated natural-language fields in English only. Preserve quoted source evidence "
        "verbatim."
    ),
    "th": (
        "ผลลัพธ์ก่อนหน้ามีอักขระที่ไม่อนุญาตสำหรับการรันนี้ กรุณาสร้างฟิลด์ข้อความที่ระบบสร้างใหม่ "
        "เป็นภาษาไทยเท่านั้น และคง quoted source evidence ไว้ตามต้นฉบับ"
    ),
}

T = TypeVar("T")


class GeneratedContentLanguageError(ValueError):
    """A user-safe failure after generated content violates its run locale."""


def validate_generated_content(
    content: T,
    *,
    locale: str,
    evidence_paths: Iterable[str] = (),
) -> T:
    """Return ``content`` unchanged unless generated fields use an unsupported script.

    Paths are top-level field names intentionally marked as quoted source
    evidence. Their complete values are excluded from validation so their text
    cannot be rewritten or rejected merely because the source is Chinese.
    """

    protected_paths = frozenset(evidence_paths)
    if _contains_unsupported_script(content, protected_paths=protected_paths):
        raise GeneratedContentLanguageError(_localized_error(locale))
    return content


def generate_locale_safe_content(
    generate_once: Callable[[str], T],
    *,
    locale: str,
    evidence_paths: Iterable[str] = (),
) -> T:
    """Generate once, retry once with a locale correction, then fail safely."""

    result = generate_once("")
    try:
        return validate_generated_content(
            result, locale=locale, evidence_paths=evidence_paths
        )
    except GeneratedContentLanguageError:
        corrected = generate_once(locale_retry_instruction(locale))
        return validate_generated_content(
            corrected, locale=locale, evidence_paths=evidence_paths
        )


def _contains_unsupported_script(value: Any, *, protected_paths: frozenset[str]) -> bool:
    if isinstance(value, str):
        return _UNSUPPORTED_GENERATED_SCRIPT.search(value) is not None
    if isinstance(value, dict):
        return any(
            key not in protected_paths
            and _contains_unsupported_script(item, protected_paths=frozenset())
            for key, item in value.items()
        )
    if isinstance(value, (list, tuple)):
        return any(
            _contains_unsupported_script(item, protected_paths=frozenset())
            for item in value
        )
    return False


def _localized_error(locale: str) -> str:
    return _CONTENT_LANGUAGE_ERRORS.get(locale, _CONTENT_LANGUAGE_ERRORS["en"])


def locale_retry_instruction(locale: str) -> str:
    return _RETRY_INSTRUCTIONS.get(locale, _RETRY_INSTRUCTIONS["en"])
