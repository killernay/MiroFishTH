import pytest

import app.services.oasis_profile_generator as profile_module
from app.services.generation_language import (
    GeneratedContentLanguageError,
    generate_locale_safe_content,
    validate_generated_content,
)
from app.services.oasis_profile_generator import OasisProfileGenerator
from app.services.report_agent import ReportAgent
from app.services.simulation_config_generator import SimulationConfigGenerator
from app.utils.locale import set_locale


def test_validator_rejects_chinese_in_generated_content():
    with pytest.raises(GeneratedContentLanguageError, match="selected language"):
        validate_generated_content({"summary": "这是生成内容"}, locale="en")


def test_validator_preserves_chinese_quoted_source_evidence():
    content = {
        "summary": "English generated summary",
        "source_evidence": {"quote": "这是原始证据"},
    }

    validated = validate_generated_content(
        content,
        locale="en",
        evidence_paths={"source_evidence"},
    )

    assert validated is content
    assert validated["source_evidence"]["quote"] == "这是原始证据"


def test_retry_uses_locale_instruction_and_returns_second_valid_output():
    instructions = []
    outputs = iter([{"content": "这是中文"}, {"content": "Thai output"}])

    result = generate_locale_safe_content(
        lambda instruction: instructions.append(instruction) or next(outputs),
        locale="en",
    )

    assert result == {"content": "Thai output"}
    assert instructions[0] == ""
    assert "English" in instructions[1]


def test_retry_failure_is_localized_and_user_safe():
    with pytest.raises(GeneratedContentLanguageError, match="เนื้อหาที่สร้าง"):
        generate_locale_safe_content(
            lambda _instruction: {"content": "这是中文"},
            locale="th",
        )


def test_persona_generator_retries_once_with_locale_correction(monkeypatch):
    class Response:
        class Choice:
            finish_reason = "stop"

        choices = [Choice()]

    messages = []
    outputs = iter([
        '{"bio": "这是中文", "persona": "这是中文"}',
        '{"bio": "English bio", "persona": "English persona"}',
    ])

    def create_completion(_client, **kwargs):
        messages.append(kwargs["messages"])
        return Response()

    monkeypatch.setattr(profile_module, "create_chat_completion", create_completion)
    monkeypatch.setattr(profile_module, "extract_chat_completion_text", lambda _response: next(outputs))
    set_locale("en")
    generator = object.__new__(OasisProfileGenerator)
    generator.client = object()
    generator.model_name = "test"

    profile = generator._generate_profile_with_llm(
        entity_name="Ada",
        entity_type="Person",
        entity_summary="Source summary",
        entity_attributes={},
        context="",
    )

    assert profile["bio"] == "English bio"
    assert len(messages) == 2
    assert "Regenerate all generated natural-language fields in English" in messages[1][0]["content"]


def test_simulation_config_generation_retries_language_violation_once():
    generator = object.__new__(SimulationConfigGenerator)
    prompts = []
    outputs = iter([{"reasoning": "这是中文"}, {"reasoning": "English reasoning"}])
    generator._call_llm_with_retry = lambda _prompt, system_prompt: prompts.append(system_prompt) or next(outputs)
    set_locale("en")

    result = generator._generate_locale_safe_json("prompt", "base prompt")

    assert result == {"reasoning": "English reasoning"}
    assert len(prompts) == 2
    assert "Regenerate all generated natural-language fields in English" in prompts[1]


def test_report_text_retries_once_before_chinese_can_be_persisted():
    class LLM:
        def __init__(self):
            self.calls = []

        def chat(self, *, messages, **_kwargs):
            self.calls.append(messages)
            return "Final Answer: English report"

    set_locale("en")
    agent = object.__new__(ReportAgent)
    agent.llm = LLM()

    result = agent._ensure_locale_safe_text("中文报告", [{"role": "user", "content": "write"}])

    assert result == "English report"
    assert len(agent.llm.calls) == 1
    assert "Regenerate all generated natural-language fields in English" in agent.llm.calls[0][-1]["content"]
