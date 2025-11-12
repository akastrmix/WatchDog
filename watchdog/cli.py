"""Command line entry point for WatchDog quick data collection."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from .collectors import XuiClient, XrayLogWatcher
from .config_loader import load_config


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="WatchDog helper CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    collect = sub.add_parser(
        "collect-once",
        help="Fetch 3x-ui client data and sample Xray logs once",
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
    collect.add_argument(
        "--include-client-ips",
        action="store_true",
        help="Query /panel/api/inbounds/clientIps for every client",
    )

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "collect-once":
        return _command_collect_once(args)

    parser.error("unknown command")
    return 1


def _command_collect_once(args: argparse.Namespace) -> int:
    config = load_config(args.config)

    output = {
        "clients": [],
        "xray_logs": [],
    }

    with XuiClient(config.xui) as client:
        for snapshot in client.list_clients():
            entry = {
                "email": snapshot.email,
                "inbound_id": snapshot.inbound_id,
                "client_id": snapshot.client_id,
                "uuid": snapshot.uuid,
                "enable": snapshot.enable,
                "total_up": snapshot.total_up,
                "total_down": snapshot.total_down,
                "total": snapshot.total,
                "last_online": snapshot.last_online,
            }
            if args.include_client_ips:
                entry["ips"] = client.fetch_client_ips(snapshot.email).get("obj")
            entry["traffic"] = client.pull_usage_stats(snapshot.email).get("obj")
            output["clients"].append(entry)

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


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
