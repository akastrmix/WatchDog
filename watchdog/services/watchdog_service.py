"""High-level orchestration service."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

from watchdog.collectors import XuiClient, XrayLogWatcher
from watchdog.config import WatchDogConfig
from watchdog.metrics import MetricsAggregator
from watchdog.notifiers import TelegramNotifier
from watchdog.rules import RuleDecision, RuleEngine
from watchdog.services.scheduler import Scheduler


@dataclass(slots=True)
class ServiceDependencies:
    """Bundle of pluggable components used by :class:`WatchDogService`."""

    xui_client: XuiClient
    log_watcher: XrayLogWatcher
    metrics: MetricsAggregator
    rules: RuleEngine
    notifier: Optional[TelegramNotifier] = None
    scheduler: Optional[Scheduler] = None


class WatchDogService:
    """Coordinates collectors, metrics, rules and notifications."""

    def __init__(self, config: WatchDogConfig, deps: ServiceDependencies) -> None:
        self._config = config
        self._deps = deps

    def bootstrap(self) -> None:
        """Prepare dependencies and register scheduler tasks."""

        raise NotImplementedError

    def process_metrics(self) -> Iterable[RuleDecision]:
        """Fetch new metrics and run them through the rule engine."""

        raise NotImplementedError

    def dispatch_notifications(self, decisions: Iterable[RuleDecision]) -> None:
        """Push relevant decisions to the notifier backend."""

        raise NotImplementedError

    def enforce(self, decisions: Iterable[RuleDecision]) -> None:
        """Apply blocking decisions via the 3x-ui API."""

        raise NotImplementedError

    def run_forever(self) -> None:
        """Start the service loop in blocking mode."""

        raise NotImplementedError
