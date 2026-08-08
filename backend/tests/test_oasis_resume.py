import json
from types import SimpleNamespace

from app.services.simulation_runner import SimulationRunner


def test_resume_oasis_environment_starts_wait_only_process(tmp_path, monkeypatch):
    simulation_id = "sim_resume"
    sim_dir = tmp_path / simulation_id
    sim_dir.mkdir()
    (sim_dir / "simulation_config.json").write_text(
        json.dumps({"simulation_id": simulation_id, "locale": "th"}),
        encoding="utf-8",
    )
    script = tmp_path / "run_parallel_simulation.py"
    script.write_text("", encoding="utf-8")
    monkeypatch.setattr(SimulationRunner, "RUN_STATE_DIR", str(tmp_path))
    monkeypatch.setattr(SimulationRunner, "SCRIPTS_DIR", str(tmp_path))
    monkeypatch.setattr(SimulationRunner, "check_env_alive", classmethod(lambda cls, _: False))

    calls = {}

    class FakeProcess:
        pid = 1234

        def poll(self):
            return None

    def fake_popen(command, **kwargs):
        calls["command"] = command
        calls["env"] = kwargs["env"]
        return FakeProcess()

    monkeypatch.setattr("app.services.simulation_runner.subprocess.Popen", fake_popen)
    result = SimulationRunner.resume_oasis_environment(simulation_id)

    assert result["resumed"] is True
    assert calls["command"][-1] == "--resume-wait"
    assert "--no-wait" not in calls["command"]
    assert calls["env"]["MIROFISH_LOCALE"] == "th"
    SimulationRunner._processes.pop(simulation_id, None)
    SimulationRunner._resume_stdout_files.pop(simulation_id, None)


def test_resume_oasis_environment_does_not_spawn_when_alive(tmp_path, monkeypatch):
    simulation_id = "sim_alive"
    sim_dir = tmp_path / simulation_id
    sim_dir.mkdir()
    (sim_dir / "simulation_config.json").write_text("{}", encoding="utf-8")
    (tmp_path / "run_parallel_simulation.py").write_text("", encoding="utf-8")
    monkeypatch.setattr(SimulationRunner, "RUN_STATE_DIR", str(tmp_path))
    monkeypatch.setattr(SimulationRunner, "SCRIPTS_DIR", str(tmp_path))
    monkeypatch.setattr(SimulationRunner, "check_env_alive", classmethod(lambda cls, _: True))

    def fail_popen(*args, **kwargs):
        raise AssertionError("must not spawn a second OASIS process")

    monkeypatch.setattr("app.services.simulation_runner.subprocess.Popen", fail_popen)
    assert SimulationRunner.resume_oasis_environment(simulation_id) == {
        "simulation_id": simulation_id,
        "resumed": False,
        "already_alive": True,
    }


def test_check_env_alive_rejects_stale_marker_without_runner_process(tmp_path, monkeypatch):
    simulation_id = "sim_stale"
    sim_dir = tmp_path / simulation_id
    sim_dir.mkdir()
    (sim_dir / "env_status.json").write_text('{"status":"alive"}', encoding="utf-8")
    monkeypatch.setattr(SimulationRunner, "RUN_STATE_DIR", str(tmp_path))
    SimulationRunner._processes.pop(simulation_id, None)
    assert SimulationRunner.check_env_alive(simulation_id) is False
