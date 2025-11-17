"""Data collection interfaces for WatchDog."""

from .xray_log_watcher import LogEvent, XrayLogWatcher
from .xray_stats_client import (
    UserTrafficSnapshot,
    XrayStatsClient,
    XrayStatsError,
)

__all__ = [
    "LogEvent",
    "XrayLogWatcher",
    "UserTrafficSnapshot",
    "XrayStatsClient",
    "XrayStatsError",
]
