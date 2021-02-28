from abc import ABCMeta
from datetime import datetime, timezone
from struct import Struct
from typing import Any, Dict, Optional, Type

from cats.headers import Headers
from cats.server.conn import Connection

__all__ = [
    'BaseRequest',
    'Request',
    'StreamRequest',
    'InputRequest',
]


class BaseRequest(dict):
    __slots__ = ('conn', 'message_id', 'headers', 'data',)
    __registry__: Dict[int, Type['BaseRequest']] = {}
    type_id: int
    struct: Struct
    HEADER_SEPARATOR = b'\x00\x00'

    def __init__(self, conn: Connection, message_id: int):
        super().__init__()
        self.conn: Connection = conn
        self.message_id = message_id
        self.headers = Headers()
        self.data = None

    def __init_subclass__(cls, /, type_id: int = 0, struct: Struct = None): ...

    @classmethod
    def get_class_by_type_id(cls, message_type: int) -> Optional[Type['BaseRequest']]: ...

    async def input(self, data: Any = None, headers: Headers = None,
                    data_type: int = None, compression: int = None) -> 'InputRequest': ...

    @classmethod
    async def recv_from_conn(cls, conn: Connection) -> 'BaseRequest':
        raise NotImplementedError


class BasicRequest(BaseRequest, metaclass=ABCMeta):
    __slots__ = ('data_type', 'data_len', 'compression')

    def __init__(self, conn: Connection, message_id: int, data_type: int, compression: int = 0, data_len: int = 0):
        self.data_len = data_len
        self.data_type = data_type
        self.compression = compression
        super().__init__(conn, message_id)

    async def recv_data(self) -> None: ...


class Request(BasicRequest, type_id=0x00, struct=Struct('>HHHQBBI')):
    __slots__ = ('handler_id', 'status', 'send_time', 'data_type', 'data_len', 'compression')

    def __init__(self, conn: Connection, message_id: int, handler_id: int, data_type: int,
                 status: int = None, send_time: datetime = None, compression: int = 0, data_len: int = 0):
        self.handler_id = handler_id
        self.status = status or 200
        self.send_time = send_time or datetime.now(timezone.utc)
        super().__init__(conn=conn, message_id=message_id,
                         compression=compression, data_type=data_type, data_len=data_len)

    @classmethod
    async def recv_from_conn(cls, conn) -> 'Request': ...


class StreamRequest(Request, type_id=0x01, struct=Struct('>HHHQBB')):
    def __init__(self, conn, message_id: int, handler_id: int, data_type: int,
                 status: int = None, send_time: datetime = None):
        super().__init__(conn, message_id, handler_id, data_type, status, send_time)

    @classmethod
    async def recv_from_conn(cls, conn: Connection) -> 'StreamRequest': ...

    async def recv_data(self) -> None: ...

    async def _recv_large_chunk(self, fh, chunk_size) -> int: ...

    async def _recv_small_chunk(self, fh, chunk_size) -> int: ...


class InputRequest(BasicRequest, type_id=0x02, struct=Struct('>HBBI')):
    @classmethod
    async def recv_from_conn(cls, conn: Connection) -> 'InputRequest': ...

    async def answer(self, data: Any = None, headers: Headers = None,
                     compression: int = None, data_type: int = None) -> None: ...


class _DownloadSpeed(BaseRequest, type_id=0x05, struct=Struct('>I')):
    @classmethod
    async def recv_from_conn(cls, conn) -> '_DownloadSpeed': ...
