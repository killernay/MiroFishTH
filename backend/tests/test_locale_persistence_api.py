import io
import json

from app import create_app
from app.api import graph as graph_api
from app.models.project import ProjectManager
from app.services.simulation_manager import SimulationManager
from app.services.simulation_runner import SimulationRunner
import app.services.simulation_runner as runner_module


def test_project_locale_is_copied_to_a_new_simulation_and_survives_reload(
    tmp_path, monkeypatch
):
    class OntologyGenerator:
        def generate(self, **_kwargs):
            return {"entity_types": [], "edge_types": [], "analysis_summary": "พร้อม"}

    monkeypatch.setattr(ProjectManager, "PROJECTS_DIR", str(tmp_path / "projects"))
    monkeypatch.setattr(
        SimulationManager, "SIMULATION_DATA_DIR", str(tmp_path / "simulations")
    )
    monkeypatch.setattr(graph_api, "OntologyGenerator", OntologyGenerator)

    app = create_app()
    app.config.update(TESTING=True)
    client = app.test_client()

    project_response = client.post(
        "/api/graph/ontology/generate",
        data={
            "simulation_requirement": "ทดสอบภาษา",
            "files": (io.BytesIO(b"source"), "source.md"),
        },
        content_type="multipart/form-data",
        headers={"Accept-Language": "th"},
    )

    assert project_response.status_code == 200
    project_id = project_response.json["data"]["project_id"]
    project = ProjectManager.get_project(project_id)
    project.graph_id = "graph-1"
    ProjectManager.save_project(project)

    simulation_response = client.post(
        "/api/simulation/create",
        json={"project_id": project_id},
        headers={"Accept-Language": "en"},
    )

    assert simulation_response.status_code == 200
    simulation_id = simulation_response.json["data"]["simulation_id"]
    reloaded_project = ProjectManager.get_project(project_id)
    reloaded_simulation = SimulationManager().get_simulation(simulation_id)

    assert reloaded_project.locale == "th"
    assert reloaded_simulation.locale == "th"


def test_run_locale_is_normalized_and_passed_to_the_simulation_subprocess(
    tmp_path, monkeypatch
):
    simulation_id = "sim-locale"
    simulation_dir = tmp_path / simulation_id
    scripts_dir = tmp_path / "scripts"
    simulation_dir.mkdir()
    scripts_dir.mkdir()
    (simulation_dir / "simulation_config.json").write_text(
        json.dumps(
            {
                "time_config": {
                    "total_simulation_hours": 1,
                    "minutes_per_round": 60,
                }
            }
        ),
        encoding="utf-8",
    )
    (scripts_dir / "run_twitter_simulation.py").write_text("pass\n", encoding="utf-8")

    captured_environment = {}

    class Process:
        pid = 123

        def poll(self):
            return None

    class Thread:
        def __init__(self, **_kwargs):
            pass

        def start(self):
            pass

    monkeypatch.setattr(SimulationRunner, "RUN_STATE_DIR", str(tmp_path))
    monkeypatch.setattr(SimulationRunner, "SCRIPTS_DIR", str(scripts_dir))
    monkeypatch.setattr(
        runner_module.subprocess,
        "Popen",
        lambda *_args, **kwargs: (
            captured_environment.update(kwargs["env"]),
            Process(),
        )[1],
    )
    monkeypatch.setattr(runner_module.threading, "Thread", Thread)
    monkeypatch.setattr(
        SimulationRunner,
        "_sync_simulation_status",
        classmethod(lambda _cls, *_args, **_kwargs: None),
    )

    try:
        state = SimulationRunner.start_simulation(
            simulation_id, platform="twitter", locale="zh-CN"
        )

        SimulationRunner._run_states.pop(simulation_id, None)
        reloaded = SimulationRunner.get_run_state(simulation_id)
        assert state.locale == "en"
        assert reloaded.locale == "en"
        assert captured_environment["MIROFISH_LOCALE"] == "en"
    finally:
        SimulationRunner._run_states.pop(simulation_id, None)
        SimulationRunner._processes.pop(simulation_id, None)
        SimulationRunner._monitor_threads.pop(simulation_id, None)
        SimulationRunner._action_queues.pop(simulation_id, None)
        SimulationRunner._graph_memory_enabled.pop(simulation_id, None)
        stdout_file = SimulationRunner._stdout_files.pop(simulation_id, None)
        if stdout_file:
            stdout_file.close()
