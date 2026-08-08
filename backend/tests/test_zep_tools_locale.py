from app.services.zep_tools import (
    AgentInterview,
    EdgeInfo,
    InsightForgeResult,
    InterviewResult,
    NodeInfo,
    PanoramaResult,
    SearchResult,
    ZepToolsService,
)
from app.utils.locale import set_locale


def test_panorama_wrapper_is_english_while_source_facts_remain_verbatim():
    set_locale("en")
    result = PanoramaResult(
        query="policy impact",
        active_facts=["这是原始证据"],
        total_nodes=2,
        total_edges=3,
        active_count=1,
    )

    text = result.to_text()

    assert "## Panorama search results" in text
    assert "Active source facts" in text
    assert "这是原始证据" in text
    assert "广度搜索结果" not in text
    assert "当前有效事实" not in text


def test_insight_and_interview_wrappers_follow_thai_locale():
    set_locale("th")

    insight_text = InsightForgeResult(
        query="ผลกระทบ",
        simulation_requirement="สถานการณ์ทดสอบ",
        sub_queries=["คำถามย่อย"],
    ).to_text()
    interview_text = InterviewResult(
        interview_topic="คำถามทดสอบ",
        interview_questions=[],
    ).to_text()

    assert "## การวิเคราะห์เชิงลึกสำหรับการคาดการณ์" in insight_text
    assert "## รายงานการสัมภาษณ์เชิงลึก" in interview_text
    assert "未来预测深度分析" not in insight_text
    assert "深度采访报告" not in interview_text


def test_search_node_edge_and_profile_wrappers_are_english():
    set_locale("en")

    search_text = SearchResult(
        query="test", facts=["这是原始证据"], edges=[], nodes=[], total_count=1
    ).to_text()
    node_text = NodeInfo("id", "name", ["Entity", "Person"], "source summary", {}).to_text()
    edge_text = EdgeInfo("id", "knows", "source fact", "a", "b").to_text(True)
    profile_text = AgentInterview("A", "Student", "source bio", "Question?", "Answer").to_text()

    assert "Search query: test" in search_text
    assert "Related source facts" in search_text
    assert "Entity: name (type: Person)" in node_text
    assert "Relation:" in edge_text
    assert "Bio: source bio" in profile_text
    assert "搜索查询" not in search_text
    assert "实体:" not in node_text
    assert "关系:" not in edge_text
    assert "简介:" not in profile_text


class _PromptCapturingLLM:
    def __init__(self):
        self.messages = []

    def chat_json(self, messages, **_kwargs):
        self.messages.append(messages)
        return {"sub_queries": ["sub-question"]}


def test_llm_system_prompts_are_english_for_an_english_run():
    set_locale("en")
    llm = _PromptCapturingLLM()
    service = ZepToolsService.__new__(ZepToolsService)
    service._llm_client = llm

    service._generate_sub_queries("policy", "scenario")
    service._select_agents_for_interview(
        [{"realname": "A", "profession": "Student"}], "topic", "scenario", 1
    )
    service._generate_interview_questions("topic", "scenario", [{"profession": "Student"}])

    prompts = "\n".join(message[0]["content"] for message in llm.messages)
    assert "你是" not in prompts
    assert "采访需求" not in prompts
    assert "模拟背景" not in prompts
