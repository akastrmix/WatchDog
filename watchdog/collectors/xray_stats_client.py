"""Client wrapper for the Xray gRPC StatsService."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, Mapping

import grpc

from watchdog.config import XrayApiConfig
from watchdog.protos import xray_stats_pb2 as stats_pb2
from watchdog.protos import xray_stats_pb2_grpc as stats_pb2_grpc


class XrayStatsError(RuntimeError):
    """Raised when the StatsService call fails."""


@dataclass(slots=True)
class UserTrafficSnapshot:
    """Cumulative uplink/downlink counters for a single user."""

    uplink: int
    downlink: int


class XrayStatsClient:
    """Lightweight helper around the ``StatsService`` gRPC API."""

    def __init__(self, config: XrayApiConfig) -> None:
        self._config = config
        self._channel = self._build_channel(config)
        self._stub = stats_pb2_grpc.StatsServiceStub(self._channel)

    @staticmethod
    def _build_channel(config: XrayApiConfig) -> grpc.Channel:
        target = f"{config.address}:{config.port}"
        if config.use_tls:
            credentials = grpc.ssl_channel_credentials()
            return grpc.secure_channel(target, credentials)
        return grpc.insecure_channel(target)

    def close(self) -> None:
        self._channel.close()

    def __enter__(self) -> "XrayStatsClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # type: ignore[override]
        self.close()

    # ------------------------------------------------------------------
    def query_user_traffic(self, *, reset: bool = False) -> Dict[str, UserTrafficSnapshot]:
        """Return cumulative uplink/downlink counters for every user."""

        response = self._call_query(pattern="user>>>*>>>traffic>>>*", reset=reset)
        buckets: Dict[str, UserTrafficSnapshot] = {}
        for stat in response.stat:
            email, direction = self._parse_user_stat_name(stat.name)
            if not email or direction not in {"uplink", "downlink"}:
                continue
            snapshot = buckets.setdefault(email, UserTrafficSnapshot(uplink=0, downlink=0))
            if direction == "uplink":
                snapshot.uplink = int(stat.value)
            else:
                snapshot.downlink = int(stat.value)
        return buckets

    def online_ips(self, stat_name: str) -> Mapping[str, int]:
        """Query ``GetStatsOnlineIpList`` for ``stat_name``."""

        request = stats_pb2.GetStatsRequest(name=stat_name)
        try:
            response = self._stub.GetStatsOnlineIpList(request, timeout=self._config.timeout)
        except grpc.RpcError as exc:  # pragma: no cover - network failure
            raise XrayStatsError(str(exc)) from exc
        return dict(response.ips)

    def _call_query(self, *, pattern: str, reset: bool) -> stats_pb2.QueryStatsResponse:
        request = stats_pb2.QueryStatsRequest(pattern=pattern, reset=reset)
        try:
            return self._stub.QueryStats(request, timeout=self._config.timeout)
        except grpc.RpcError as exc:  # pragma: no cover - network failure
            raise XrayStatsError(str(exc)) from exc

    @staticmethod
    def _parse_user_stat_name(name: str) -> tuple[str, str]:
        parts = name.split(">>>")
        if len(parts) < 3:
            return "", ""
        scope = parts[0].lower()
        if scope != "user":
            return "", ""
        email = parts[1]
        if len(parts) == 3:
            metric = parts[2].lower()
            return email, metric
        category = parts[2].lower()
        metric = parts[3].lower()
        if category != "traffic":
            return "", ""
        return email, metric


__all__ = ["UserTrafficSnapshot", "XrayStatsClient", "XrayStatsError"]
