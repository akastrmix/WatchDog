"""Streaming helper for Xray access logs."""
from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Optional

from watchdog.config import XrayLogSource


@dataclass(slots=True)
class LogEvent:
    """Represents a single Xray access log entry in a normalised structure."""

    email: str
    ip: str
    target: str
    bytes_read: int
    bytes_written: int
    metadata: Dict[str, object]


_ADDR_PATTERN = re.compile(r"\[(?P<ipv6>[^\]]+)\]|(?P<ipv4>\d+\.\d+\.\d+\.\d+)")


class XrayLogWatcher:
    """Tail and parse Xray logs.

    The parser supports both structured JSON logs and the simplified text format
    exposed by the ``/panel/api/server/xraylogs/{count}`` endpoint.  The JSON
    parsing logic follows the documented fields in
    https://xtls.github.io/config/log.html#logobject.  Additional keys are
    preserved inside ``metadata`` so downstream components can access the full
    record if required.
    """

    def __init__(self, source: XrayLogSource) -> None:
        self._source = source

    # ------------------------------------------------------------------
    def stream(self) -> Iterator[LogEvent]:
        """Yield log events as they are appended to the log file."""

        path = Path(self._source.access_log)
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            if self._source.follow:
                handle.seek(0, os.SEEK_END)
            while True:
                position = handle.tell()
                line = handle.readline()
                if not line:
                    time.sleep(0.5)
                    handle.seek(position)
                    continue
                event = self._parse_line(line)
                if event:
                    yield event

    def snapshot(self, limit: Optional[int] = None) -> Iterable[LogEvent]:
        """Return the most recent log events from the configured file."""

        path = Path(self._source.access_log)
        lines = self._read_lines(path)
        if limit is not None:
            lines = lines[-limit:]
        events: List[LogEvent] = []
        for line in lines:
            event = self._parse_line(line)
            if event:
                events.append(event)
        return events

    # ------------------------------------------------------------------
    def _read_lines(self, path: Path) -> List[str]:
        if not path.exists():
            raise FileNotFoundError(f"Xray access log not found: {path}")
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            return handle.readlines()

    def _parse_line(self, line: str) -> Optional[LogEvent]:
        line = line.strip()
        if not line:
            return None

        if self._source.is_json:
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                return None
            return self._normalise_record(record)

        # ``xraylogs`` endpoint delivers JSON even though the access log may be
        # configured as plain text.  To remain compatible we first try to parse
        # JSON, then fall back to storing the raw message.
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            return LogEvent(
                email="",
                ip="",
                target="",
                bytes_read=0,
                bytes_written=0,
                metadata={"raw": line},
            )
        return self._normalise_record(record)

    def _normalise_record(self, record: Dict[str, object]) -> LogEvent:
        metadata = dict(record)
        email = self._extract_email(record)
        ip = self._extract_ip(record)
        target = self._extract_target(record)
        bytes_read, bytes_written = self._extract_traffic(record)
        return LogEvent(
            email=email,
            ip=ip,
            target=target,
            bytes_read=bytes_read,
            bytes_written=bytes_written,
            metadata=metadata,
        )

    @staticmethod
    def _extract_email(record: Dict[str, object]) -> str:
        candidates = [
            record.get("email"),
            record.get("Email"),
            record.get("user"),
            record.get("clientEmail"),
            record.get("client"),
        ]
        session = record.get("session")
        if isinstance(session, dict):
            candidates.append(session.get("email"))
            candidates.append(session.get("user"))
        account = record.get("account")
        if isinstance(account, dict):
            candidates.append(account.get("email"))
        for candidate in candidates:
            if isinstance(candidate, str) and candidate:
                return candidate
        return ""

    @staticmethod
    def _extract_ip(record: Dict[str, object]) -> str:
        candidates = [
            record.get("ip"),
            record.get("IP"),
            record.get("remote"),
            record.get("remote_addr"),
            record.get("clientIP"),
            record.get("FromAddress"),
            record.get("from"),
        ]
        session = record.get("session")
        if isinstance(session, dict):
            candidates.append(session.get("ip"))
        for candidate in candidates:
            if isinstance(candidate, str) and candidate:
                match = _ADDR_PATTERN.search(candidate)
                if match:
                    return match.group("ipv6") or match.group("ipv4") or ""
                return candidate
        return ""

    @staticmethod
    def _extract_target(record: Dict[str, object]) -> str:
        candidates = [
            record.get("target"),
            record.get("ToAddress"),
            record.get("to"),
            record.get("destination"),
            record.get("request"),
        ]
        for candidate in candidates:
            if isinstance(candidate, str) and candidate:
                return candidate
        session = record.get("session")
        if isinstance(session, dict):
            target = session.get("target")
            if isinstance(target, str):
                return target
        return ""

    @staticmethod
    def _extract_traffic(record: Dict[str, object]) -> tuple[int, int]:
        uplink_keys = ("uplink", "upLink", "uplinkBytes", "uplink_bytes", "up")
        downlink_keys = (
            "downlink",
            "downLink",
            "downlinkBytes",
            "downlink_bytes",
            "down",
        )

        up = XrayLogWatcher._lookup_numeric(record, uplink_keys)
        down = XrayLogWatcher._lookup_numeric(record, downlink_keys)
        traffic = record.get("traffic")
        if isinstance(traffic, dict):
            up = up or XrayLogWatcher._lookup_numeric(traffic, uplink_keys)
            down = down or XrayLogWatcher._lookup_numeric(traffic, downlink_keys)
        return up or 0, down or 0

    @staticmethod
    def _lookup_numeric(source: Dict[str, object], keys: Iterable[str]) -> Optional[int]:
        for key in keys:
            value = source.get(key)
            if isinstance(value, int):
                return value
            if isinstance(value, str) and value.isdigit():
                return int(value)
        return None
