"""Deep OASIS session interface over the file-backed IPC adapter."""

from typing import Any, Optional

from .simulation_ipc import SimulationIPCClient


class OASISSession:
    """Owns liveness and command ordering for one simulation environment."""

    def __init__(self, simulation_dir: str, client: Optional[SimulationIPCClient] = None):
        self.client = client or SimulationIPCClient(simulation_dir)

    def is_alive(self) -> bool:
        return self.client.check_env_alive()

    def interview(self, agent_id: int, prompt: str, platform: Optional[str] = None, timeout: float = 60.0):
        self._require_alive()
        return self.client.send_interview(agent_id, prompt, platform, timeout)

    def batch_interview(self, interviews: list[dict[str, Any]], platform: Optional[str] = None, timeout: float = 120.0):
        self._require_alive()
        return self.client.send_batch_interview(interviews, platform, timeout)

    def close(self, timeout: float = 30.0):
        self._require_alive()
        return self.client.send_close_env(timeout)

    def _require_alive(self) -> None:
        if not self.is_alive():
            raise ValueError("The OASIS simulation environment is not running")
