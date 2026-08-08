from app.services.zep_graph_memory_updater import AgentActivity
from app.utils.locale import set_locale


def _activity(action_type, action_args):
    return AgentActivity(
        platform="twitter",
        agent_id=1,
        agent_name="Agent A",
        action_type=action_type,
        action_args=action_args,
        round_num=2,
        timestamp="2026-08-08T12:00:00Z",
    )


def test_episode_uses_english_system_text_and_preserves_source_post():
    set_locale("en")

    episode = _activity("CREATE_POST", {"content": "原始โพสต์"}).to_episode_text()

    assert "Agent A: posted: \"原始โพสต์\"" in episode
    assert "发布了一条帖子" not in episode


def test_episode_uses_thai_system_text_and_preserves_source_comment():
    set_locale("th")

    episode = _activity(
        "CREATE_COMMENT",
        {"post_author_name": "B", "post_content": "原始โพสต์", "content": "คำตอบเดิม"},
    ).to_episode_text()

    assert 'แสดงความคิดเห็นต่อโพสต์ของ B "原始โพสต์": "คำตอบเดิม"' in episode
    assert "在" not in episode
    assert "评论道" not in episode
