"""Single source of truth for persisted simulation run phases."""

from dataclasses import dataclass
from enum import Enum
from typing import Any


class RunPhase(str, Enum):
    IDLE = "not_started"
    RUNNING = "running"
    AWAITING_FINISH = "awaiting_finish"
    FINISHING = "finishing"
    REPORT_READY = "report_ready"
    FAILED = "failed"


@dataclass(frozen=True)
class RunLifecycle:
    phase: RunPhase
    environment_alive: bool
    report_completed: bool
    report_active: bool

    @property
    def can_interview(self) -> bool:
        return self.environment_alive and self.phase in {
            RunPhase.AWAITING_FINISH,
            RunPhase.REPORT_READY,
        }

    @property
    def can_report(self) -> bool:
        return self.phase in {RunPhase.AWAITING_FINISH, RunPhase.REPORT_READY}

    @property
    def can_finish(self) -> bool:
        return self.report_completed and not self.report_active


def _platforms_complete(run_state: Any) -> bool:
    enabled = []
    for prefix in ("twitter", "reddit"):
        active = bool(
            getattr(run_state, f"{prefix}_completed", False)
            or getattr(run_state, f"{prefix}_running", False)
            or getattr(run_state, f"{prefix}_actions_count", 0)
        )
        if active:
            enabled.append(bool(getattr(run_state, f"{prefix}_completed", False)))
    return bool(enabled) and all(enabled)


def derive_lifecycle(run_state: Any, *, environment_alive: bool, report_completed: bool = False, report_active: bool = False) -> RunLifecycle:
    if run_state is None:
        return RunLifecycle(RunPhase.IDLE, environment_alive, report_completed, report_active)
    status = getattr(getattr(run_state, "runner_status", None), "value", getattr(run_state, "runner_status", "idle"))
    if status == "failed":
        phase = RunPhase.FAILED
    elif status in {"completed", "stopped"}:
        phase = RunPhase.REPORT_READY
    elif status == "stopping":
        phase = RunPhase.FINISHING
    elif status == "running" and _platforms_complete(run_state):
        phase = RunPhase.AWAITING_FINISH
    elif status == "running":
        phase = RunPhase.RUNNING
    else:
        phase = RunPhase.IDLE
    return RunLifecycle(phase, environment_alive, report_completed, report_active)
