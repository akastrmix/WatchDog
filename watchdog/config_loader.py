"""Utilities to load :mod:`watchdog.config` structures from YAML files."""
from __future__ import annotations

import datetime as _dt
from pathlib import Path
from typing import Any, Mapping

import yaml

from .config import (
    MetricWindow,
    MetricsConfig,
    RuleProfile,
    RulesConfig,
    SchedulerConfig,
    TelegramConfig,
    WatchDogConfig,
    XrayLogSource,
    XuiCredentials,
)

_DURATION_UNITS = {
    "s": _dt.timedelta(seconds=1),
    "m": _dt.timedelta(minutes=1),
    "h": _dt.timedelta(hours=1),
    "d": _dt.timedelta(days=1),
}


def load_config(path: Path) -> WatchDogConfig:
    """Load a configuration file into :class:`WatchDogConfig`.

    The loader accepts human friendly values such as ``"30s"`` or ``"5m"`` for
    durations and converts them into :class:`datetime.timedelta` objects.  Fields
    omitted in the YAML file fall back to the defaults declared in
    :mod:`watchdog.config`.
    """

    raw = _load_yaml(path)

    xui = XuiCredentials(
        base_url=str(raw["xui"]["base_url"]),
        username=str(raw["xui"]["username"]),
        password=str(raw["xui"]["password"]),
        request_timeout=float(raw["xui"].get("request_timeout", 5.0)),
    )

    xray_section = raw.get("xray", {})
    xray = XrayLogSource(
        access_log=Path(xray_section["access_log"]),
        error_log=Path(xray_section["error_log"]) if xray_section.get("error_log") else None,
        is_json=bool(xray_section.get("is_json", True)),
        follow=bool(xray_section.get("follow", True)),
    )

    metrics_section = raw.get("metrics", {})
    metric_windows = [
        MetricWindow(label=entry["label"], duration=_parse_duration(entry["duration"]))
        for entry in metrics_section.get("windows", [])
    ]
    metrics = MetricsConfig(
        windows=tuple(metric_windows) if metric_windows else MetricsConfig().windows,
        retention=_parse_duration(metrics_section.get("retention", "7d")),
    )

    rules_section = raw.get("rules", {})
    profiles = [
        RuleProfile(
            name=item["name"],
            connection_threshold=int(item["connection_threshold"]),
            burst_bytes=int(item["burst_bytes"]),
            unique_ip_threshold=int(item["unique_ip_threshold"]),
            restricted_targets=tuple(item.get("restricted_targets", [])),
            score_threshold=float(item.get("score_threshold", 1.0)),
        )
        for item in rules_section.get("profiles", [])
    ]
    rules = RulesConfig(
        default_profile=rules_section.get("default_profile", profiles[0].name if profiles else "default"),
        profiles=tuple(profiles) if profiles else (RuleProfile(
            name="default",
            connection_threshold=100,
            burst_bytes=500_000_000,
            unique_ip_threshold=20,
            restricted_targets=(),
            score_threshold=1.0,
        ),),
    )

    telegram_cfg = None
    if "telegram" in raw and raw["telegram"]:
        telegram_cfg = TelegramConfig(
            bot_token=str(raw["telegram"]["bot_token"]),
            chat_ids=tuple(int(cid) for cid in raw["telegram"].get("chat_ids", [])),
            notify_on_warning=bool(raw["telegram"].get("notify_on_warning", True)),
            notify_on_block=bool(raw["telegram"].get("notify_on_block", True)),
            dry_run=bool(raw["telegram"].get("dry_run", False)),
        )

    scheduler_section = raw.get("scheduler", {})
    scheduler = SchedulerConfig(
        poll_interval=_parse_duration(scheduler_section.get("poll_interval", "30s")),
        log_scan_interval=_parse_duration(scheduler_section.get("log_scan_interval", "10s")),
    )

    state_dir = Path(raw.get("state_dir", "./state"))

    return WatchDogConfig(
        xui=xui,
        xray=xray,
        metrics=metrics,
        rules=rules,
        telegram=telegram_cfg,
        scheduler=scheduler,
        state_dir=state_dir,
    )


def _load_yaml(path: Path) -> Mapping[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, Mapping):
        raise ValueError("configuration root must be a mapping")
    return data


def _parse_duration(value: Any) -> _dt.timedelta:
    if isinstance(value, _dt.timedelta):
        return value
    if isinstance(value, (int, float)):
        return _dt.timedelta(seconds=float(value))
    if not isinstance(value, str):
        raise ValueError(f"unsupported duration value: {value!r}")
    value = value.strip()
    if value.isdigit():
        return _dt.timedelta(seconds=int(value))
    unit = value[-1].lower()
    if unit not in _DURATION_UNITS:
        raise ValueError(f"unknown duration unit: {value}")
    amount = float(value[:-1])
    base = _DURATION_UNITS[unit]
    return _dt.timedelta(seconds=base.total_seconds() * amount)
