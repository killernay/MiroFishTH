import importlib.util
import json
import sys
import types
import ast
from pathlib import Path

import pytest


SCRIPTS_DIR = Path(__file__).parents[1] / "scripts"


class _ActionType:
    CREATE_POST = LIKE_POST = REPOST = FOLLOW = DO_NOTHING = QUOTE_POST = "action"
    DISLIKE_POST = CREATE_COMMENT = LIKE_COMMENT = DISLIKE_COMMENT = "action"
    SEARCH_POSTS = SEARCH_USER = TREND = REFRESH = MUTE = INTERVIEW = "action"


def _load_script(monkeypatch, filename):
    monkeypatch.syspath_prepend(str(SCRIPTS_DIR))
    monkeypatch.setitem(sys.modules, "dotenv", types.SimpleNamespace(load_dotenv=lambda *_: None))
    monkeypatch.setitem(
        sys.modules,
        "action_logger",
        types.SimpleNamespace(SimulationLogManager=object, PlatformActionLogger=object),
    )
    monkeypatch.setitem(sys.modules, "camel.models", types.SimpleNamespace(ModelFactory=object))
    monkeypatch.setitem(sys.modules, "camel.types", types.SimpleNamespace(ModelPlatformType=object))
    monkeypatch.setitem(
        sys.modules,
        "oasis",
        types.SimpleNamespace(
            ActionType=_ActionType,
            LLMAction=object,
            ManualAction=object,
            generate_twitter_agent_graph=object,
            generate_reddit_agent_graph=object,
        ),
    )

    spec = importlib.util.spec_from_file_location(
        f"oasis_{filename}_script_for_test", SCRIPTS_DIR / filename
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    "filename",
    ["run_parallel_simulation.py", "run_twitter_simulation.py", "run_reddit_simulation.py"],
)
def test_oasis_scripts_use_persisted_locale_before_environment_for_system_output(
    tmp_path, monkeypatch, filename
):
    module = _load_script(monkeypatch, filename)
    config_path = tmp_path / "simulation_config.json"
    config_path.write_text(json.dumps({"locale": "th"}), encoding="utf-8")
    monkeypatch.setenv("MIROFISH_LOCALE", "en")

    if hasattr(module, "load_config"):
        module.configure_system_locale(module.load_config(str(config_path)))
    else:
        runner_class = getattr(module, "TwitterSimulationRunner", None) or module.RedditSimulationRunner
        runner_class(str(config_path), wait_for_commands=False)

    assert module.system_message("Simulation complete", "การจำลองเสร็จสมบูรณ์") == "การจำลองเสร็จสมบูรณ์"


def test_parallel_script_uses_environment_locale_when_legacy_config_has_no_locale(monkeypatch):
    module = _load_script(monkeypatch, "run_parallel_simulation.py")
    monkeypatch.setenv("MIROFISH_LOCALE", "th")

    module.configure_system_locale({})

    assert module.system_message("Simulation complete", "การจำลองเสร็จสมบูรณ์") == "การจำลองเสร็จสมบูรณ์"


def test_resumed_interview_reads_resume_database(monkeypatch):
    module = _load_script(monkeypatch, "run_parallel_simulation.py")
    source = (SCRIPTS_DIR / "run_parallel_simulation.py").read_text(encoding="utf-8")
    assert 'f"{platform}_resume.db"' in source
    assert "resume_db_path if os.path.exists(resume_db_path)" in source


@pytest.mark.parametrize(
    "filename",
    ["run_parallel_simulation.py", "run_twitter_simulation.py", "run_reddit_simulation.py"],
)
def test_every_script_authored_print_fragment_is_localized_without_han(monkeypatch, filename):
    module = _load_script(monkeypatch, filename)
    tree = ast.parse((SCRIPTS_DIR / filename).read_text(encoding="utf-8"))
    fragments = []

    for call in ast.walk(tree):
        if not isinstance(call, ast.Call) or not isinstance(call.func, ast.Name) or call.func.id != "print":
            continue
        fragments.extend(
            node.value
            for argument in call.args
            for node in ast.walk(argument)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        )

    assert fragments
    unlocalized = [
        fragment
        for fragment in fragments
        if any("\u4e00" <= char <= "\u9fff" for char in module.localize_system_output(fragment))
    ]
    assert not unlocalized
