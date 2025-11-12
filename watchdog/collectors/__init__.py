"""Data collection interfaces for WatchDog."""

from .xui_client import (
    ClientSnapshot,
    XuiAuthenticationError,
    XuiClient,
    XuiError,
)
from .xray_log_watcher import LogEvent, XrayLogWatcher

__all__ = [
    "ClientSnapshot",
    "XuiAuthenticationError",
    "XuiClient",
    "XuiError",
    "LogEvent",
    "XrayLogWatcher",
]
