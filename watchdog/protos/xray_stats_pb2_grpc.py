"""gRPC client and server stubs for the Xray StatsService."""

from __future__ import annotations

import grpc

from . import xray_stats_pb2 as xray_stats__pb2


class StatsServiceStub:
    """Client stub for calling the StatsService endpoints."""

    def __init__(self, channel: grpc.Channel) -> None:
        self.GetStats = channel.unary_unary(
            "/xray.app.stats.command.StatsService/GetStats",
            request_serializer=xray_stats__pb2.GetStatsRequest.SerializeToString,
            response_deserializer=xray_stats__pb2.GetStatsResponse.FromString,
        )
        self.GetStatsOnline = channel.unary_unary(
            "/xray.app.stats.command.StatsService/GetStatsOnline",
            request_serializer=xray_stats__pb2.GetStatsRequest.SerializeToString,
            response_deserializer=xray_stats__pb2.GetStatsResponse.FromString,
        )
        self.QueryStats = channel.unary_unary(
            "/xray.app.stats.command.StatsService/QueryStats",
            request_serializer=xray_stats__pb2.QueryStatsRequest.SerializeToString,
            response_deserializer=xray_stats__pb2.QueryStatsResponse.FromString,
        )
        self.GetStatsOnlineIpList = channel.unary_unary(
            "/xray.app.stats.command.StatsService/GetStatsOnlineIpList",
            request_serializer=xray_stats__pb2.GetStatsRequest.SerializeToString,
            response_deserializer=xray_stats__pb2.GetStatsOnlineIpListResponse.FromString,
        )


__all__ = ["StatsServiceStub"]
