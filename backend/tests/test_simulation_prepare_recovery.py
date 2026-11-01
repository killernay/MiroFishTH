import json

from app.api import simulation as simulation_api


def test_prepared_check_recovers_complete_artifacts_with_stale_metadata(
    monkeypatch, tmp_path
):
    simulation_id = "sim-recovery"
    simulation_dir = tmp_path / simulation_id
    simulation_dir.mkdir()
    (simulation_dir / "reddit_profiles.json").write_text(
        json.dumps([{"name": "Agent"}]), encoding="utf-8"
    )
    (simulation_dir / "twitter_profiles.csv").write_text(
        "name\nAgent\n", encoding="utf-8"
    )
    (simulation_dir / "simulation_config.json").write_text(
        json.dumps({"time_config": {"total_simulation_hours": 24}}),
        encoding="utf-8",
    )
    state_file = simulation_dir / "state.json"
    state_file.write_text(
        json.dumps({
            "status": "preparing",
            "config_generated": False,
            "profiles_generated": False,
            "profiles_count": 0,
        }),
        encoding="utf-8",
    )
    monkeypatch.setattr(simulation_api.Config, "OASIS_SIMULATION_DATA_DIR", str(tmp_path))

    prepared, info = simulation_api._check_simulation_prepared(simulation_id)

    assert prepared is True
    assert info["status"] == "ready"
    assert info["config_generated"] is True
    recovered = json.loads(state_file.read_text(encoding="utf-8"))
    assert recovered["status"] == "ready"
    assert recovered["profiles_generated"] is True
    assert recovered["profiles_count"] == 1
    assert recovered["config_generated"] is True
