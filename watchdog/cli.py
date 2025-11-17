"""Command line entry point for WatchDog quick data collection."""
from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from .collectors import XrayLogWatcher, XrayStatsClient
from .config_loader import load_config
from .metrics import MetricsAggregator


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="WatchDog helper CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    collect = sub.add_parser(
        "collect-once",
        help="Fetch Xray stats and sample logs once",
    )
    collect.add_argument(
        "--config",
        type=Path,
        required=True,
        help="Path to the YAML configuration file",
    )
    collect.add_argument(
        "--xray-limit",
        type=int,
        default=20,
        help="How many recent Xray log entries to include in the output",
    )

    metrics = sub.add_parser(
        "collect-metrics",
        help="Run a short-lived metrics sampling session",
    )
    metrics.add_argument(
        "--config",
        type=Path,
        required=True,
        help="Path to the YAML configuration file",
    )
    metrics.add_argument(
        "--duration",
        type=int,
        default=120,
        help="How many seconds to sample metrics for (default: 120)",
    )

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "collect-once":
        return _command_collect_once(args)
    if args.command == "collect-metrics":
        return _command_collect_metrics(args)

    parser.error("unknown command")
    return 1


def _command_collect_once(args: argparse.Namespace) -> int:
    config = load_config(args.config)

    output = {
        "user_traffic": [],
        "xray_logs": [],
    }

    with XrayStatsClient(config.xray_api) as stats_client:
        counters = stats_client.query_user_traffic()
        for email in sorted(counters):
            snapshot = counters[email]
            output["user_traffic"].append(
                {
                    "email": email,
                    "uplink": snapshot.uplink,
                    "downlink": snapshot.downlink,
                }
            )

    watcher = XrayLogWatcher(config.xray)
    for event in watcher.snapshot(limit=args.xray_limit):
        output["xray_logs"].append(
            {
                "email": event.email,
                "ip": event.ip,
                "target": event.target,
                "bytes_read": event.bytes_read,
                "bytes_written": event.bytes_written,
                "metadata": event.metadata,
            }
        )

    print(json.dumps(output, indent=2, ensure_ascii=False))
    return 0


def _command_collect_metrics(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    duration = max(10, int(args.duration))
    bucket_seconds = int(config.metrics.bucket_interval.total_seconds())
    aggregator = MetricsAggregator(config.metrics)

    stop_event = threading.Event()
    watcher = XrayLogWatcher(config.xray)
    log_thread = threading.Thread(
        target=_log_tail_worker, args=(watcher, aggregator, stop_event), daemon=True
    )
    log_thread.start()

    try:
        with XrayStatsClient(config.xray_api) as stats_client:
            end_time = time.monotonic() + duration
            next_tick = time.monotonic()
            while time.monotonic() < end_time:
                now = datetime.now(timezone.utc)
                counters = stats_client.query_user_traffic()
                aggregator.record_user_counters(now, counters)
                aggregator.purge_expired(now)
                next_tick += bucket_seconds
                sleep_for = max(0.0, next_tick - time.monotonic())
                time.sleep(sleep_for)
    except KeyboardInterrupt:  # pragma: no cover - interactive use
        print("Interrupted, compiling snapshot...", file=sys.stderr)
    finally:
        stop_event.set()
        log_thread.join(timeout=2)

    snapshot = aggregator.snapshot()
    print(json.dumps(snapshot.to_dict(), indent=2, ensure_ascii=False))
    return 0


def _log_tail_worker(
    watcher: XrayLogWatcher, aggregator: MetricsAggregator, stop_event: threading.Event
) -> None:
    try:
        for event in watcher.stream(stop_event=stop_event):
            aggregator.record_log_events([event])
            if stop_event.is_set():
                break
    except FileNotFoundError as exc:  # pragma: no cover - depends on host setup
        print(f"Xray log not found: {exc}", file=sys.stderr)
        stop_event.set()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
