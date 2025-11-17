"""Streaming helper for Xray access logs."""
from __future__ import annotations

import json
import os
import re
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Optional

from watchdog.config import XrayLogSource


@dataclass(slots=True)
class LogEvent:
    """Represents a single Xray access log entry in a normalised structure."""

    timestamp: datetime
    email: str
    ip: str
    target: str
    transport: str
    target_host: str
    target_port: Optional[int]
    status: str
    bytes_read: int
    bytes_written: int
    metadata: Dict[str, object]


_ADDR_PATTERN = re.compile(r"\[(?P<ipv6>[^\]]+)\]|(?P<ipv4>\d+\.\d+\.\d+\.\d+)")

_TEXT_LINE_PATTERNS = (
    re.compile(
        r"""
        ^(?P<date>\d{4}/\d{2}/\d{2})\s+
        (?P<time>\d{2}:\d{2}:\d{2}(?:\.\d+)?)\s+
        (?P<source>[^\s]+)\s+
        (?P<status>accepted|rejected)\s+
        (?P<target>[^\s]+)
        (?:\s+\[(?P<detour>[^\]]+)\])?
        (?:\s+(?P<rest>.*))?
        $
        """,
        re.VERBOSE,
    ),
    re.compile(
        r"""
        ^(?P<date>\d{4}/\d{2}/\d{2})\s+
        (?P<time>\d{2}:\d{2}:\d{2}(?:\.\d+)?)\s+
        from\s+(?P<source>[^\s]+)\s+
        (?P<status>accepted|rejected)\s+
        (?P<target>[^\s]+)
        (?:\s+\[(?P<detour>[^\]]+)\])?
        (?:\s+(?P<rest>.*))?
        $
        """,
        re.VERBOSE,
    ),
)

_EMAIL_PATTERN = re.compile(r"email:\s*(?P<email>\S+)")

_KEY_VALUE_PATTERN = re.compile(
    r"(?P<key>[A-Za-z0-9_\-]+):\s*(?P<value>.+?)(?=(?:\s+[A-Za-z0-9_\-]+:)|$)"
)


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
    def stream(self, stop_event: Optional[threading.Event] = None) -> Iterator[LogEvent]:
        """Yield log events as they are appended to the log file."""

        path = Path(self._source.access_log)
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            if self._source.follow:
                handle.seek(0, os.SEEK_END)
            while True:
                if stop_event and stop_event.is_set():
                    break
                position = handle.tell()
                line = handle.readline()
                if not line:
                    if stop_event and stop_event.is_set():
                        break
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

        text_event = self._parse_text_line(line)
        if text_event:
            return text_event

        # ``xraylogs`` endpoint delivers JSON even though the access log may be
        # configured as plain text.  To remain compatible we first try to parse
        # JSON, then fall back to storing the raw message.
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            return self._build_event(
                timestamp=self._now(),
                email="",
                ip="",
                target="",
                transport="",
                host="",
                port=None,
                status="",
                bytes_read=0,
                bytes_written=0,
                metadata={"raw": line},
            )
        return self._normalise_record(record)

    def _parse_text_line(self, line: str) -> Optional[LogEvent]:
        match = None
        for pattern in _TEXT_LINE_PATTERNS:
            match = pattern.match(line)
            if match:
                break
        if match is None:
            return None

        source = match.group("source")
        target = match.group("target")
        rest = (match.group("rest") or "").strip()
        timestamp = self._parse_timestamp_string(match.group("date"), match.group("time"))
        status = (match.group("status") or "").strip()
        email = ""
        reason = ""
        metadata: Dict[str, object] = {
            "timestamp": f"{match.group('date')} {match.group('time')}",
            "status": match.group("status"),
            "source": source,
            "target": target,
            "raw": line,
        }

        if rest:
            key_values = list(_KEY_VALUE_PATTERN.finditer(rest))
            consumed_ranges: List[tuple[int, int]] = []
            for kv in key_values:
                key = kv.group("key")
                value = kv.group("value").strip()
                consumed_ranges.append((kv.start(), kv.end()))
                lowered = key.lower()
                if lowered == "email":
                    email = value
                elif lowered == "reason":
                    reason = value
                else:
                    metadata[key] = value

            # Whatever is left after removing the captured ``key: value``
            # pairs is treated as a free-form reason string.
            if not reason:
                remaining = rest
                for start, end in reversed(consumed_ranges):
                    remaining = remaining[:start] + remaining[end:]
                remaining = remaining.strip()
                if remaining:
                    reason = remaining
            if not email:
                email_match = _EMAIL_PATTERN.search(rest)
                if email_match:
                    email = email_match.group("email")

        ip = self._extract_address(source)

        detour = match.group("detour")
        if detour:
            metadata["detour"] = detour
        if reason:
            metadata["reason"] = reason
        if email:
            metadata["email"] = email

        transport, host, port = self._split_target_fields(target)
        if transport:
            metadata["transport"] = transport
        if host:
            metadata["host"] = host
        if port is not None:
            metadata["port"] = port

        # 3x-ui proxies management API calls through Xray which results in
        # synthetic loopback entries (``api -> api``).  They carry no customer
        # traffic information and would otherwise pollute the data set, so drop
        # them during normalisation.
        if (
            metadata.get("detour") == "api -> api"
            and metadata["source"].startswith("127.0.0.1:")
            and target.startswith("tcp:127.0.0.1:")
        ):
            return None

        return self._build_event(
            timestamp=timestamp,
            email=email,
            ip=ip,
            target=target,
            transport=transport,
            host=host,
            port=port,
            status=status,
            bytes_read=0,
            bytes_written=0,
            metadata=metadata,
        )

    @staticmethod
    def _extract_address(value: str) -> str:
        match = _ADDR_PATTERN.search(value)
        if match:
            return match.group("ipv6") or match.group("ipv4") or ""
        if ":" in value:
            return value.split(":", 1)[0]
        return value

    @staticmethod
    def _split_target_fields(value: str) -> tuple[str, str, Optional[int]]:
        """Split ``value`` into transport, host and port components."""

        transport = ""
        remainder = value

        if remainder.startswith(("tcp:", "udp:", "unix:")):
            transport, _, remainder = remainder.partition(":")

        host = remainder
        port: Optional[int] = None

        if remainder.startswith("["):
            end = remainder.find("]")
            if end != -1:
                host = remainder[1:end]
                rest = remainder[end + 1 :]
                if rest.startswith(":") and rest[1:].isdigit():
                    port = int(rest[1:])
        elif ":" in remainder:
            host, sep, maybe_port = remainder.rpartition(":")
            if sep and maybe_port.isdigit():
                port = int(maybe_port)
            else:
                host = remainder

        return transport, host, port

    def _parse_timestamp_string(self, date_str: str, time_str: str) -> datetime:
        raw = f"{date_str} {time_str}"
        for fmt in ("%Y/%m/%d %H:%M:%S.%f", "%Y/%m/%d %H:%M:%S"):
            try:
                return datetime.strptime(raw, fmt).replace(tzinfo=timezone.utc)
            except ValueError:
                continue
        return self._now()

    def _extract_timestamp(self, record: Dict[str, object]) -> datetime:
        candidates: List[str] = []
        for key in ("timestamp", "time", "event_time", "ts"):
            value = record.get(key)
            if isinstance(value, str) and value:
                candidates.append(value)
        for candidate in candidates:
            parsed = self._parse_generic_timestamp(candidate)
            if parsed:
                return parsed
        return self._now()

    @staticmethod
    def _parse_generic_timestamp(value: str) -> Optional[datetime]:
        trimmed = value.strip()
        iso_candidate = trimmed.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(iso_candidate)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed
        except ValueError:
            pass
        for fmt in ("%Y/%m/%d %H:%M:%S.%f", "%Y/%m/%d %H:%M:%S"):
            try:
                return datetime.strptime(trimmed, fmt).replace(tzinfo=timezone.utc)
            except ValueError:
                continue
        return None

    def _normalise_record(self, record: Dict[str, object]) -> Optional[LogEvent]:
        metadata = dict(record)
        email = self._extract_email(record)
        ip = self._extract_ip(record)
        target = self._extract_target(record)
        bytes_read, bytes_written = self._extract_traffic(record)
        transport, host, port = self._split_target_fields(target)
        if transport and "transport" not in metadata:
            metadata["transport"] = transport
        if host and "host" not in metadata:
            metadata["host"] = host
        if port is not None and "port" not in metadata:
            metadata["port"] = port
        status = self._extract_status(record)
        timestamp = self._extract_timestamp(record)
        return self._build_event(
            timestamp=timestamp,
            email=email,
            ip=ip,
            target=target,
            transport=transport,
            host=host,
            port=port,
            status=status,
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

    def _build_event(
        self,
        *,
        timestamp: datetime,
        email: str,
        ip: str,
        target: str,
        transport: str,
        host: str,
        port: Optional[int],
        status: str,
        bytes_read: int,
        bytes_written: int,
        metadata: Dict[str, object],
    ) -> Optional[LogEvent]:
        if self._is_internal_api_log(metadata=metadata, target=target, ip=ip):
            return None

        return LogEvent(
            timestamp=timestamp,
            email=email,
            ip=ip,
            target=target,
            transport=transport,
            target_host=host,
            target_port=port,
            status=status,
            bytes_read=bytes_read,
            bytes_written=bytes_written,
            metadata=metadata,
        )

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

    @staticmethod
    def _extract_status(record: Dict[str, object]) -> str:
        for key in ("status", "action", "event"):
            value = record.get(key)
            if isinstance(value, str) and value:
                return value
        return ""

    def _is_internal_api_log(
        self, *, metadata: Dict[str, object], target: str, ip: str
    ) -> bool:
        detour = metadata.get("detour") or metadata.get("tag")
        if not isinstance(detour, str):
            return False

        detour_lower = detour.lower()
        if "api" not in detour_lower:
            return False

        target_host = self._host_from_metadata(metadata, target)
        if target_host and self._address_is_loopback(target_host):
            return True

        source_candidates = [
            metadata.get("source"),
            metadata.get("from"),
            metadata.get("client"),
        ]

        for candidate in source_candidates:
            if isinstance(candidate, str) and self._address_is_loopback(candidate):
                return True

        if ip and self._address_is_loopback(ip):
            return True

        return False

    def _host_from_metadata(self, metadata: Dict[str, object], target: str) -> str:
        host = ""
        target_value = metadata.get("target")
        if isinstance(target_value, str):
            _, host, _ = self._split_target_fields(target_value)
        if not host and target:
            _, host, _ = self._split_target_fields(target)
        host_value = metadata.get("host")
        if not host and isinstance(host_value, str):
            host = host_value
        return host

    @staticmethod
    def _address_is_loopback(value: str) -> bool:
        if not value:
            return False

        address = XrayLogWatcher._extract_address(value)
        if not address:
            return False

        if address.startswith("127.") or address == "::1":
            return True

        if address.lower() == "localhost":
            return True

        return False

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)
