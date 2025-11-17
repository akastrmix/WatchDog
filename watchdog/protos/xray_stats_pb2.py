"""Minimal protobuf definitions for Xray's StatsService."""

from __future__ import annotations

from google.protobuf import descriptor as _descriptor
from google.protobuf import descriptor_pool as _descriptor_pool
from google.protobuf import message as _message
from google.protobuf import reflection as _reflection
from google.protobuf import symbol_database as _symbol_database
from google.protobuf import descriptor_pb2

_sym_db = _symbol_database.Default()


def _build_file_descriptor() -> _descriptor.FileDescriptor:
    file_proto = descriptor_pb2.FileDescriptorProto()
    file_proto.name = "xray_stats.proto"
    file_proto.package = "xray.app.stats.command"
    file_proto.syntax = "proto3"

    # GetStatsRequest
    msg = file_proto.message_type.add()
    msg.name = "GetStatsRequest"
    field = msg.field.add()
    field.name = "name"
    field.number = 1
    field.label = field.LABEL_OPTIONAL
    field.type = field.TYPE_STRING
    field = msg.field.add()
    field.name = "reset"
    field.number = 2
    field.label = field.LABEL_OPTIONAL
    field.type = field.TYPE_BOOL

    # Stat
    msg = file_proto.message_type.add()
    msg.name = "Stat"
    field = msg.field.add()
    field.name = "name"
    field.number = 1
    field.label = field.LABEL_OPTIONAL
    field.type = field.TYPE_STRING
    field = msg.field.add()
    field.name = "value"
    field.number = 2
    field.label = field.LABEL_OPTIONAL
    field.type = field.TYPE_INT64

    # GetStatsResponse
    msg = file_proto.message_type.add()
    msg.name = "GetStatsResponse"
    field = msg.field.add()
    field.name = "stat"
    field.number = 1
    field.label = field.LABEL_OPTIONAL
    field.type = field.TYPE_MESSAGE
    field.type_name = "Stat"

    # QueryStatsRequest
    msg = file_proto.message_type.add()
    msg.name = "QueryStatsRequest"
    field = msg.field.add()
    field.name = "pattern"
    field.number = 1
    field.label = field.LABEL_OPTIONAL
    field.type = field.TYPE_STRING
    field = msg.field.add()
    field.name = "reset"
    field.number = 2
    field.label = field.LABEL_OPTIONAL
    field.type = field.TYPE_BOOL

    # QueryStatsResponse
    msg = file_proto.message_type.add()
    msg.name = "QueryStatsResponse"
    field = msg.field.add()
    field.name = "stat"
    field.number = 1
    field.label = field.LABEL_REPEATED
    field.type = field.TYPE_MESSAGE
    field.type_name = "Stat"

    # GetStatsOnlineIpListResponse with map field
    msg = file_proto.message_type.add()
    msg.name = "GetStatsOnlineIpListResponse"
    field = msg.field.add()
    field.name = "name"
    field.number = 1
    field.label = field.LABEL_OPTIONAL
    field.type = field.TYPE_STRING
    field = msg.field.add()
    field.name = "ips"
    field.number = 2
    field.label = field.LABEL_REPEATED
    field.type = field.TYPE_MESSAGE
    field.type_name = "GetStatsOnlineIpListResponse.IpsEntry"

    entry = msg.nested_type.add()
    entry.name = "IpsEntry"
    entry.options.map_entry = True
    f = entry.field.add()
    f.name = "key"
    f.number = 1
    f.label = f.LABEL_OPTIONAL
    f.type = f.TYPE_STRING
    f = entry.field.add()
    f.name = "value"
    f.number = 2
    f.label = f.LABEL_OPTIONAL
    f.type = f.TYPE_INT64

    # Service declaration (needed for gRPC stubs)
    service = file_proto.service.add()
    service.name = "StatsService"

    method = service.method.add()
    method.name = "GetStats"
    method.input_type = "GetStatsRequest"
    method.output_type = "GetStatsResponse"

    method = service.method.add()
    method.name = "GetStatsOnline"
    method.input_type = "GetStatsRequest"
    method.output_type = "GetStatsResponse"

    method = service.method.add()
    method.name = "QueryStats"
    method.input_type = "QueryStatsRequest"
    method.output_type = "QueryStatsResponse"

    method = service.method.add()
    method.name = "GetStatsOnlineIpList"
    method.input_type = "GetStatsRequest"
    method.output_type = "GetStatsOnlineIpListResponse"

    return _descriptor_pool.Default().AddSerializedFile(file_proto.SerializeToString())


DESCRIPTOR = _build_file_descriptor()

GETSTATSREQUEST = DESCRIPTOR.message_types_by_name["GetStatsRequest"]
STAT = DESCRIPTOR.message_types_by_name["Stat"]
GETSTATSRESPONSE = DESCRIPTOR.message_types_by_name["GetStatsResponse"]
QUERYSTATSREQUEST = DESCRIPTOR.message_types_by_name["QueryStatsRequest"]
QUERYSTATSRESPONSE = DESCRIPTOR.message_types_by_name["QueryStatsResponse"]
GETSTATSONLINEIPLISTRESPONSE = DESCRIPTOR.message_types_by_name["GetStatsOnlineIpListResponse"]
GETSTATSONLINEIPLISTRESPONSE_IPSENTRY = GETSTATSONLINEIPLISTRESPONSE.nested_types_by_name["IpsEntry"]


class GetStatsRequest(_message.Message, metaclass=_reflection.GeneratedProtocolMessageType):
    DESCRIPTOR = GETSTATSREQUEST


class Stat(_message.Message, metaclass=_reflection.GeneratedProtocolMessageType):
    DESCRIPTOR = STAT


class GetStatsResponse(_message.Message, metaclass=_reflection.GeneratedProtocolMessageType):
    DESCRIPTOR = GETSTATSRESPONSE


class QueryStatsRequest(_message.Message, metaclass=_reflection.GeneratedProtocolMessageType):
    DESCRIPTOR = QUERYSTATSREQUEST


class QueryStatsResponse(_message.Message, metaclass=_reflection.GeneratedProtocolMessageType):
    DESCRIPTOR = QUERYSTATSRESPONSE


class GetStatsOnlineIpListResponse(_message.Message, metaclass=_reflection.GeneratedProtocolMessageType):
    DESCRIPTOR = GETSTATSONLINEIPLISTRESPONSE

    class IpsEntry(_message.Message, metaclass=_reflection.GeneratedProtocolMessageType):
        DESCRIPTOR = GETSTATSONLINEIPLISTRESPONSE_IPSENTRY


_sym_db.RegisterMessage(GetStatsRequest)
_sym_db.RegisterMessage(Stat)
_sym_db.RegisterMessage(GetStatsResponse)
_sym_db.RegisterMessage(QueryStatsRequest)
_sym_db.RegisterMessage(QueryStatsResponse)
_sym_db.RegisterMessage(GetStatsOnlineIpListResponse)
_sym_db.RegisterMessage(GetStatsOnlineIpListResponse.IpsEntry)


__all__ = [
    "DESCRIPTOR",
    "GetStatsRequest",
    "GetStatsResponse",
    "GetStatsOnlineIpListResponse",
    "QueryStatsRequest",
    "QueryStatsResponse",
    "Stat",
]
