"""Shared policy for system-generated output and quoted source evidence."""

from .generation_language import validate_generated_content
from ..utils.logger import redact_han_text


def sanitize_system_output(text: str) -> str:
    return redact_han_text(text)


def validate_generated(text: str, locale: str) -> None:
    validate_generated_content(text, locale=locale)
