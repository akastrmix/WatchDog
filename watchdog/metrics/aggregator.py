"""Bucket-based metric aggregation for users and source IPs."""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Dict, Iterable, Mapping, MutableMapping, Optional, Tuple

from watchdog.collectors.xray_log_watcher import LogEvent
from watchdog.collectors.xray_stats_client import UserTrafficSnapshot
from watchdog.config import MetricsConfig


@dataclass(slots=True)
class UserBucket:
    """Aggregated metrics for a user within a single time bucket."""

    email: str
    bucket_start: datetime
    up_bytes: int
    down_bytes: int
    conn_total: int
    conn_tcp: int
    conn_udp: int
    unique_ips: int
    ip_breakdown: Mapping[str, int]
    host_breakdown: Mapping[str, int]
    rejects: int

    def to_dict(self) -> Dict[str, object]:
        return {
            "email": self.email,
            "bucket": self.bucket_start.isoformat(),
            "up_bytes": self.up_bytes,
            "down_bytes": self.down_bytes,
            "conn_total": self.conn_total,
            "conn_tcp": self.conn_tcp,
            "conn_udp": self.conn_udp,
            "unique_ips": self.unique_ips,
            "ip_breakdown": dict(self.ip_breakdown),
            "host_breakdown": dict(self.host_breakdown),
            "rejects": self.rejects,
        }


@dataclass(slots=True)
class IpBucket:
    """Aggregated metrics for a source IP within a time bucket."""

    ip: str
    bucket_start: datetime
    bytes_total: int
    byte_source: str
    conn_total: int
    users: Mapping[str, int]
    host_breakdown: Mapping[str, int]

    def to_dict(self) -> Dict[str, object]:
        return {
            "ip": self.ip,
            "bucket": self.bucket_start.isoformat(),
            "bytes_total": self.bytes_total,
            "byte_source": self.byte_source,
            "conn_total": self.conn_total,
            "users": dict(self.users),
            "host_breakdown": dict(self.host_breakdown),
        }


@dataclass(slots=True)
class MetricsSnapshot:
    """Serializable container for the aggregated metrics."""

    generated_at: datetime
    bucket_seconds: int
    users: Iterable[UserBucket]
    ips: Iterable[IpBucket]

    def to_dict(self) -> Dict[str, object]:
        return {
            "generated_at": self.generated_at.isoformat(),
            "bucket_seconds": self.bucket_seconds,
            "users": [bucket.to_dict() for bucket in self.users],
            "ips": [bucket.to_dict() for bucket in self.ips],
        }


class MetricsAggregator:
    """Maintain rolling per-user and per-IP 10s buckets, retaining 24h of data."""

    def __init__(self, config: MetricsConfig) -> None:
        bucket_seconds = int(config.bucket_interval.total_seconds())
        if bucket_seconds <= 0:
            raise ValueError("bucket interval must be positive")
        self._bucket_seconds = bucket_seconds
        self._retention = config.retention
        self._user_state: Dict[Tuple[str, int], _MutableUserBucket] = {}
        self._ip_state: Dict[Tuple[str, int], _MutableIpBucket] = {}
        self._user_totals: Dict[str, Tuple[int, int]] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    def record_user_counters(
        self, timestamp: datetime, counters: Mapping[str, UserTrafficSnapshot]
    ) -> None:
        bucket_epoch, bucket_start = self._bucket_key(timestamp)
        with self._lock:
            for email, snapshot in counters.items():
                prev_up, prev_down = self._user_totals.get(email, (snapshot.uplink, snapshot.downlink))
                up_delta = self._compute_delta(snapshot.uplink, prev_up)
                down_delta = self._compute_delta(snapshot.downlink, prev_down)
                self._user_totals[email] = (snapshot.uplink, snapshot.downlink)
                if up_delta == 0 and down_delta == 0:
                    continue
                bucket = self._user_state.setdefault(
                    (email, bucket_epoch),
                    _MutableUserBucket(email=email, bucket_epoch=bucket_epoch, bucket_start=bucket_start),
                )
                bucket.up_bytes += up_delta
                bucket.down_bytes += down_delta

    def record_log_events(self, events: Iterable[LogEvent]) -> None:
        with self._lock:
            for event in events:
                bucket_epoch, bucket_start = self._bucket_key(event.timestamp)
                host_label = event.target_host or event.target
                if event.email:
                    bucket = self._user_state.setdefault(
                        (event.email, bucket_epoch),
                        _MutableUserBucket(event.email, bucket_epoch, bucket_start),
                    )
                    bucket.conn_total += 1
                    transport = (event.transport or "").lower()
                    if transport == "udp":
                        bucket.conn_udp += 1
                    else:
                        bucket.conn_tcp += 1
                    bucket.ip_counts[event.ip] = bucket.ip_counts.get(event.ip, 0) + 1
                    bucket.host_counts[host_label] = bucket.host_counts.get(host_label, 0) + 1
                    bucket.ip_set.add(event.ip)
                    if event.status and event.status.lower() != "accepted":
                        bucket.rejects += 1

                if not event.ip:
                    continue
                ip_bucket = self._ip_state.setdefault(
                    (event.ip, bucket_epoch),
                    _MutableIpBucket(event.ip, bucket_epoch, bucket_start),
                )
                ip_bucket.conn_total += 1
                if event.email:
                    ip_bucket.users[event.email] = ip_bucket.users.get(event.email, 0) + 1
                ip_bucket.host_counts[host_label] = ip_bucket.host_counts.get(host_label, 0) + 1

    def record_ip_counters(self, timestamp: datetime, counters: Mapping[str, int]) -> None:
        bucket_epoch, bucket_start = self._bucket_key(timestamp)
        with self._lock:
            for ip, value in counters.items():
                bucket = self._ip_state.setdefault(
                    (ip, bucket_epoch),
                    _MutableIpBucket(ip, bucket_epoch, bucket_start),
                )
                bucket.measured_bytes += max(0, int(value))

    def purge_expired(self, as_of: datetime) -> None:
        cutoff_epoch = self._bucket_epoch(as_of - self._retention)
        with self._lock:
            self._purge_locked(cutoff_epoch)

    def snapshot(self) -> MetricsSnapshot:
        now = datetime.now(timezone.utc)
        cutoff_epoch = self._bucket_epoch(now - self._retention)
        with self._lock:
            self._purge_locked(cutoff_epoch)
            user_buckets = [bucket.freeze() for bucket in self._user_state.values()]
            ip_state_copy = {key: bucket for key, bucket in self._ip_state.items()}

        self._distribute_estimated_ip_bytes(user_buckets, ip_state_copy)

        user_buckets.sort(key=lambda item: (item.bucket_start, item.email))
        ip_buckets = [bucket.freeze() for bucket in ip_state_copy.values()]
        ip_buckets.sort(key=lambda item: (item.bucket_start, item.ip))

        return MetricsSnapshot(
            generated_at=now,
            bucket_seconds=self._bucket_seconds,
            users=user_buckets,
            ips=ip_buckets,
        )

    # ------------------------------------------------------------------
    def _purge_locked(self, cutoff_epoch: int) -> None:
        expired = [key for key, bucket in self._user_state.items() if bucket.bucket_epoch < cutoff_epoch]
        for key in expired:
            del self._user_state[key]
        expired = [key for key, bucket in self._ip_state.items() if bucket.bucket_epoch < cutoff_epoch]
        for key in expired:
            del self._ip_state[key]

    def _bucket_key(self, timestamp: datetime) -> Tuple[int, datetime]:
        epoch = self._bucket_epoch(timestamp)
        bucket_start = datetime.fromtimestamp(epoch, tz=timezone.utc)
        return epoch, bucket_start

    def _bucket_epoch(self, timestamp: datetime) -> int:
        ts = timestamp
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        seconds = int(ts.timestamp())
        return (seconds // self._bucket_seconds) * self._bucket_seconds

    @staticmethod
    def _compute_delta(current: int, previous: int) -> int:
        current = max(0, int(current))
        previous = max(0, int(previous))
        if current >= previous:
            return current - previous
        return current

    def _distribute_estimated_ip_bytes(
        self, user_buckets: Iterable[UserBucket], ip_state: MutableMapping[Tuple[str, int], "_MutableIpBucket"]
    ) -> None:
        for bucket in user_buckets:
            total_bytes = bucket.up_bytes + bucket.down_bytes
            if total_bytes <= 0:
                continue
            total_connections = bucket.conn_total or sum(bucket.ip_breakdown.values())
            if total_connections <= 0:
                continue
            bucket_epoch = self._bucket_epoch(bucket.bucket_start)
            for ip, count in bucket.ip_breakdown.items():
                share = (total_bytes * count) / total_connections
                target = ip_state.setdefault(
                    (ip, bucket_epoch),
                    _MutableIpBucket(ip, bucket_epoch, bucket.bucket_start),
                )
                target.estimated_bytes += int(share)


@dataclass(slots=True)
class _MutableUserBucket:
    email: str
    bucket_epoch: int
    bucket_start: datetime
    up_bytes: int = 0
    down_bytes: int = 0
    conn_total: int = 0
    conn_tcp: int = 0
    conn_udp: int = 0
    rejects: int = 0
    ip_counts: Dict[str, int] = field(default_factory=dict)
    host_counts: Dict[str, int] = field(default_factory=dict)
    ip_set: set = field(default_factory=set)

    def freeze(self) -> UserBucket:
        return UserBucket(
            email=self.email,
            bucket_start=self.bucket_start,
            up_bytes=self.up_bytes,
            down_bytes=self.down_bytes,
            conn_total=self.conn_total,
            conn_tcp=self.conn_tcp,
            conn_udp=self.conn_udp,
            unique_ips=len([ip for ip in self.ip_set if ip]),
            ip_breakdown=dict(self.ip_counts),
            host_breakdown=dict(self.host_counts),
            rejects=self.rejects,
        )


@dataclass(slots=True)
class _MutableIpBucket:
    ip: str
    bucket_epoch: int
    bucket_start: datetime
    measured_bytes: int = 0
    estimated_bytes: int = 0
    conn_total: int = 0
    users: Dict[str, int] = field(default_factory=dict)
    host_counts: Dict[str, int] = field(default_factory=dict)

    def freeze(self) -> IpBucket:
        bytes_total = self.measured_bytes if self.measured_bytes else self.estimated_bytes
        byte_source = "measured" if self.measured_bytes else "estimated"
        return IpBucket(
            ip=self.ip,
            bucket_start=self.bucket_start,
            bytes_total=bytes_total,
            byte_source=byte_source,
            conn_total=self.conn_total,
            users=dict(self.users),
            host_breakdown=dict(self.host_counts),
        )


__all__ = [
    "IpBucket",
    "MetricsAggregator",
    "MetricsSnapshot",
    "UserBucket",
]
