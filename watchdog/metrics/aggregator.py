"""Client-level metric aggregation primitives."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Mapping

from watchdog.collectors.xray_log_watcher import LogEvent
from watchdog.config import MetricWindow, MetricsConfig


@dataclass(slots=True)
class ClientMetrics:
    """Aggregated metrics for a client within a time window."""

    email: str
    window: str
    total_connections: int
    unique_ips: int
    total_bytes: int
    targets: Mapping[str, int]


class MetricsAggregator:
    """Aggregate raw log events into :class:`ClientMetrics` instances."""

    def __init__(self, config: MetricsConfig) -> None:
        self._config = config

    def ingest(self, events: Iterable[LogEvent]) -> None:
        """Add a batch of events into the aggregator state."""

        raise NotImplementedError

    def compute(self, window: MetricWindow, as_of: datetime) -> Iterable[ClientMetrics]:
        """Produce metrics for the given window ending at ``as_of``."""

        raise NotImplementedError

    def purge_expired(self, as_of: datetime) -> None:
        """Drop in-memory state that falls outside the retention window."""

        raise NotImplementedError
