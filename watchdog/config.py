"""Configuration schema for WatchDog independent deployment.

This module defines dataclasses that describe how the watchdog core is
configured when it runs alongside a single 3x-ui/Xray node.  The goal is to
standardise configuration while keeping it easy to extend as the project
matures.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path
from typing import Optional, Sequence


@dataclass(slots=True)
class XuiCredentials:
    """Authentication configuration for the 3x-ui API."""

    base_url: str
    username: str
    password: str
    request_timeout: float = 5.0


@dataclass(slots=True)
class XrayLogSource:
    """Location and format hints for Xray log files."""

    access_log: Path
    error_log: Optional[Path] = None
    is_json: bool = False
    follow: bool = True


@dataclass(slots=True)
class XrayApiConfig:
    """Connection parameters for the Xray gRPC API service."""

    address: str = "127.0.0.1"
    port: int = 62789
    use_tls: bool = False
    timeout: float = 5.0


@dataclass(slots=True)
class MetricWindow:
    """Time window used when aggregating metrics for a client."""

    label: str
    duration: timedelta


@dataclass(slots=True)
class MetricsConfig:
    """Configuration for metric aggregation and retention."""

    windows: Sequence[MetricWindow] = field(
        default_factory=lambda: (
            MetricWindow(label="1m", duration=timedelta(minutes=1)),
            MetricWindow(label="5m", duration=timedelta(minutes=5)),
            MetricWindow(label="1h", duration=timedelta(hours=1)),
        )
    )
    retention: timedelta = timedelta(days=7)
    bucket_interval: timedelta = timedelta(seconds=10)


@dataclass(slots=True)
class RuleProfile:
    """Named configuration profile for abuse detection rules."""

    name: str
    connection_threshold: int
    burst_bytes: int
    unique_ip_threshold: int
    restricted_targets: Sequence[str] = field(default_factory=tuple)
    score_threshold: float = 1.0


@dataclass(slots=True)
class RulesConfig:
    """Container for multiple rule profiles."""

    default_profile: str
    profiles: Sequence[RuleProfile]


@dataclass(slots=True)
class TelegramConfig:
    """Outgoing Telegram bot integration."""

    bot_token: str
    chat_ids: Sequence[int]
    notify_on_warning: bool = True
    notify_on_block: bool = True
    dry_run: bool = False


@dataclass(slots=True)
class SchedulerConfig:
    """Timing knobs for the background scheduler."""

    poll_interval: timedelta = timedelta(seconds=30)
    log_scan_interval: timedelta = timedelta(seconds=10)


@dataclass(slots=True)
class WatchDogConfig:
    """Top-level configuration bundle for an independent deployment."""

    xui: XuiCredentials
    xray: XrayLogSource
    xray_api: XrayApiConfig = field(default_factory=XrayApiConfig)
    metrics: MetricsConfig
    rules: RulesConfig
    telegram: Optional[TelegramConfig] = None
    scheduler: SchedulerConfig = field(default_factory=SchedulerConfig)
    state_dir: Path = field(default_factory=lambda: Path("./state"))

