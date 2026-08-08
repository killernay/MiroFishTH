import pytest

import app.services.oasis_profile_generator as profile_module
from app.services.generation_language import (
    GeneratedContentLanguageError,
    generate_locale_safe_content,
    validate_generated_content,
)
from app.services.oasis_profile_generator import OasisProfileGenerator
from app.services.report_agent import ReportAgent, ReportManager, ReportSection
from app.services.simulation_config_generator import SimulationConfigGenerator
from app.utils.locale import set_locale


def test_validator_rejects_chinese_in_generated_content():
    with pytest.raises(GeneratedContentLanguageError, match="selected language"):
        validate_generated_content({"summary": "这是生成内容"}, locale="en")


@pytest.mark.parametrize(
    "generated_text",
    [
        "𠀀",  # CJK Unified Ideographs Extension B
        "これは日本語です",  # Hiragana and Han
        "한국어 생성 내용",  # Hangul
        "Сгенерированный текст",  # Cyrillic
    ],
)
def test_validator_rejects_non_english_thai_generated_scripts(generated_text):
    with pytest.raises(GeneratedContentLanguageError, match="selected language"):
        validate_generated_content({"summary": generated_text}, locale="en")


def test_validator_preserves_normal_punctuation_numbers_and_thai():
    content = {"summary": "รุ่น 2.0 — ราคา 1,250 บาท (50%)!"}

    assert validate_generated_content(content, locale="th") is content


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


def test_persona_generator_uses_safe_fallback_for_missing_generated_fields(monkeypatch):
    class Response:
        class Choice:
            finish_reason = "stop"

        choices = [Choice()]

    monkeypatch.setattr(profile_module, "create_chat_completion", lambda *_args, **_kwargs: Response())
    monkeypatch.setattr(
        profile_module, "extract_chat_completion_text", lambda _response: '{"bio": "", "persona": ""}'
    )
    set_locale("en")
    generator = object.__new__(OasisProfileGenerator)
    generator.client = object()
    generator.model_name = "test"
    source_summary = "Raw source summary: 这是原始摘要"

    profile = generator._generate_profile_with_llm(
        entity_name="Example", entity_type="Person", entity_summary=source_summary,
        entity_attributes={}, context="",
    )

    assert profile["bio"] == "Social discussion participant."
    assert profile["persona"] == "This account participates in social discussions in its assigned role."


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


def test_report_chat_keeps_tagged_source_evidence_verbatim_with_an_english_label():
    class LLM:
        def __init__(self):
            self.responses = iter([
                '<tool_call>{"name":"quick_search","parameters":{"query":"source"}}</tool_call>',
                "Conclusion: stable. <source_evidence>这是原始证据</source_evidence>",
            ])

        def chat(self, **_kwargs):
            return next(self.responses)

    set_locale("en")
    agent = object.__new__(ReportAgent)
    agent.llm = LLM()
    agent.simulation_id = "sim-test"
    agent.simulation_requirement = "Test scenario"
    agent.tools = {}
    agent._execute_tool = lambda *_args, **_kwargs: "这是原始证据"

    result = agent.chat("What happened?")

    assert result["response"] == (
        "Conclusion: stable. **[Quoted source evidence]**\n\n```text\n"
        "这是原始证据\n```"
    )


def test_report_chat_uses_the_thai_evidence_label_for_a_thai_run():
    class LLM:
        def __init__(self):
            self.responses = iter([
                '<tool_call>{"name":"quick_search","parameters":{"query":"source"}}</tool_call>',
                "ข้อสรุปมีเสถียรภาพ <source_evidence>这是原始证据</source_evidence>",
            ])

        def chat(self, **_kwargs):
            return next(self.responses)

    set_locale("th")
    agent = object.__new__(ReportAgent)
    agent.llm = LLM()
    agent.simulation_id = "sim-test"
    agent.simulation_requirement = "สถานการณ์ทดสอบ"
    agent.tools = {}
    agent._execute_tool = lambda *_args, **_kwargs: "这是原始证据"

    result = agent.chat("เกิดอะไรขึ้น?")

    assert "**[หลักฐานจากแหล่งข้อมูลที่อ้างอิง]**" in result["response"]
    assert "这是原始证据" in result["response"]


def test_report_retries_when_model_marks_unverified_chinese_as_source_evidence():
    class LLM:
        def __init__(self):
            self.calls = []

        def chat(self, *, messages, **_kwargs):
            self.calls.append(messages)
            return "English report"

    set_locale("en")
    agent = object.__new__(ReportAgent)
    agent.llm = LLM()

    result = agent._ensure_locale_safe_text(
        "<source_evidence>这是模型生成的中文</source_evidence>",
        [{"role": "user", "content": "write"}],
    )

    assert result == "English report"
    assert len(agent.llm.calls) == 1


def test_saved_section_preserves_markdown_like_source_evidence_verbatim(tmp_path, monkeypatch):
    set_locale("en")
    monkeypatch.setattr(ReportManager, "REPORTS_DIR", str(tmp_path))
    evidence = "## 原始标题\n这是原始证据"
    section = ReportSection(
        title="Findings",
        content=(
            "Conclusion. **[Quoted source evidence]**\n\n```text\n"
            f"{evidence}\n```"
        ),
    )

    path = ReportManager.save_section("report-test", 1, section)

    with open(path, encoding="utf-8") as saved_section:
        assert evidence in saved_section.read()
