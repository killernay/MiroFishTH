from types import SimpleNamespace

from app.services.evidence_ledger import EvidenceLedger
from app.services.run_lifecycle import RunPhase, derive_lifecycle
from app.services.oasis_session import OASISSession
from app.utils.zep_lifecycle import PersistentGraphReadLeaseStore


def test_run_lifecycle_keeps_live_oasis_in_interview_phase():
    state = SimpleNamespace(
        runner_status="running",
        twitter_completed=True,
        reddit_completed=True,
        twitter_actions_count=10,
        reddit_actions_count=10,
    )
    lifecycle = derive_lifecycle(state, environment_alive=True)
    assert lifecycle.phase is RunPhase.AWAITING_FINISH
    assert lifecycle.can_interview is True
    assert lifecycle.can_report is True
    assert lifecycle.can_finish is False


def test_evidence_ledger_matches_markdown_without_trusting_unrecorded_text():
    ledger = EvidenceLedger()
    ledger.record("Original source line", source_id="tool-1", tool_name="quick_search")
    assert ledger.match("```text\n> Original source line\n```").source_id == "tool-1"
    assert ledger.match("Invented source line") is None


def test_oasis_session_rejects_commands_after_environment_closes():
    class FakeClient:
        def check_env_alive(self):
            return False

    session = OASISSession("/tmp/unused", client=FakeClient())
    try:
        session.interview(1, "question")
    except ValueError as error:
        assert "not running" in str(error)
    else:
        raise AssertionError("closed OASIS must reject interview commands")


def test_graph_read_lease_store_survives_a_new_adapter(tmp_path):
    path = str(tmp_path / "leases.sqlite3")
    first = PersistentGraphReadLeaseStore(path)
    first.register("graph-1", "report-1", 4102444800)
    second = PersistentGraphReadLeaseStore(path)
    assert second.readers("graph-1") == ["report-1"]
    second.unregister("graph-1", "report-1")
    assert first.readers("graph-1") == []
