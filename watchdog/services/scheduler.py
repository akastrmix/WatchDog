"""Background scheduling primitives."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from watchdog.config import SchedulerConfig

Task = Callable[[], None]


@dataclass(slots=True)
class ScheduledTask:
    """Represents a background task with its cadence."""

    name: str
    interval_seconds: float
    task: Task


class Scheduler:
    """Very small abstraction over a cooperative scheduler.

    The concrete implementation will likely rely on ``asyncio`` or a threaded
    scheduler such as ``APScheduler``.  We only define the interface to make the
    integration points explicit.
    """

    def __init__(self, config: SchedulerConfig) -> None:
        self._config = config

    def add_task(self, scheduled_task: ScheduledTask) -> None:
        """Register a new periodic task."""

        raise NotImplementedError

    def run_forever(self) -> None:
        """Start the scheduler loop."""

        raise NotImplementedError
