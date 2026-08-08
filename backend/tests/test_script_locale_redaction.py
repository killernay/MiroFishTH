import importlib.util
from pathlib import Path


def _load(name):
    path = Path(__file__).parents[1] / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_script_output_redacts_unmapped_han_text():
    for name in ("run_parallel_simulation", "run_twitter_simulation", "run_reddit_simulation"):
        module = _load(name)
        output = module.localize_system_output("Interview failed: 未知第三方错误")
        assert "未知" not in output
        assert "第三方" not in output
        assert "[source text]" in output
