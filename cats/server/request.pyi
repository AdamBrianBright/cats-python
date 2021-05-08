from abc import ABCMeta
from asyncio import Future, Task
from datetime import datetime, timezone
from struct import Struct
from typing import Any, Dict, Optional, Type, Union

from cats.headers import Headers, T_Headers
from cats.server.conn import Connection
from cats.typing import PingData

__all__ = [
    'Input',
    'BaseRequest',
    'Request',
    'StreamRequest',
    'InputRequest',
    'DownloadSpeed',
    'CancelInput',
    'Ping',
]


class Input:
    def __init__(self, future: Future, timeout: Optional[int], conn: Connection, message_id: int, bypass_count: bool):
        self.future: Future = future
        self.timer: Optional[Task] = None
        self.conn: Connection = conn
        self.message_id: int = message_id
        self.bypass_count: bool = bypass_count
        if timeout:
            self.timer = self.conn.loop.call_later(timeout, self.cancel)

    def cancel(self): ...


class BaseRequest(dict):
    __slots__ = ('conn', 'message_id', 'headers', 'data',)
    __registry__: Dict[int, Type['BaseRequest']] = {}
    type_id: int
    struct: Struct
    HEADER_SEPARATOR = b'\x00\x00'
    status: Union[property, int]

    def __init__(self, conn: Connection, message_id: int, *, headers: T_Headers = None, status: int = 200):
        super().__init__()
        self.conn: Connection = conn
        self.message_id = message_id
        self.headers = Headers(headers or {})
        self.status = self.headers.get('Status', status or 200)
        self.data = None

    def __init_subclass__(cls, /, type_id: int = 0, struct: Struct = None): ...

    @classmethod
    def get_class_by_type_id(cls, message_type: int) -> Optional[Type['BaseRequest']]: ...

    async def input(self, data: Any = None, data_type: int = None, compression: int = None, *,
                    headers: T_Headers = None, status: int = None,
                    bypass_limit: bool = False, bypass_count: bool = False,
                    timeout: Union[int, float] = None) -> 'InputRequest': ...

    @classmethod
    async def recv_from_conn(cls, conn: Connection) -> 'BaseRequest':
        raise NotImplementedError


class BasicRequest(BaseRequest, metaclass=ABCMeta):
    __slots__ = ('data_type', 'data_len', 'compression')

    def __init__(self, conn: Connection, message_id: int, data_type: int, compression: int = 0, data_len: int = 0, *,
                 headers: T_Headers = None, status: int = None):
        self.data_len = data_len
        self.data_type = data_type
        self.compression = compression
        super().__init__(conn, message_id, headers=headers, status=status)

    async def recv_data(self) -> None: ...


class Request(BasicRequest, type_id=0x00, struct=Struct('>HHQBBI')):
    __slots__ = ('handler_id', 'send_time', 'data_type', 'data_len', 'compression')

    def __init__(self, conn: Connection, message_id: int, handler_id: int, data_type: int,
                 send_time: datetime = None, compression: int = 0, data_len: int = 0, *,
                 headers: T_Headers = None, status: int = None):
        self.handler_id = handler_id
        self.send_time = send_time or datetime.now(timezone.utc)
        super().__init__(conn=conn, message_id=message_id,
                         compression=compression, data_type=data_type, data_len=data_len,
                         headers=headers, status=status)

    @classmethod
    async def recv_from_conn(cls, conn) -> 'Request': ...


class StreamRequest(Request, type_id=0x01, struct=Struct('>HHQBB')):
    def __init__(self, conn, message_id: int, handler_id: int, data_type: int, send_time: datetime = None, *,
                 headers: T_Headers = None, status: int = None):
        super().__init__(conn, message_id, handler_id, data_type, send_time, headers=headers, status=status)

    @classmethod
    async def recv_from_conn(cls, conn: Connection) -> 'StreamRequest': ...

    async def recv_data(self) -> None: ...

    async def _recv_large_chunk(self, fh, chunk_size) -> int: ...

    async def _recv_small_chunk(self, fh, chunk_size) -> int: ...


class InputRequest(BasicRequest, type_id=0x02, struct=Struct('>HBBI')):
    @classmethod
    async def recv_from_conn(cls, conn: Connection) -> 'InputRequest': ...

    async def answer(self, data: Any = None, compression: int = None, data_type: int = None, *,
                     headers: T_Headers = None, status: int = None) -> None: ...

    async def cancel(self) -> None: ...


class CancelInput(BaseRequest, type_id=0x06, struct=Struct('>H')):
    @classmethod
    async def recv_from_conn(cls, conn: Connection): ...


class DownloadSpeed(BaseRequest, type_id=0x05, struct=Struct('>I')):
    @classmethod
    async def recv_from_conn(cls, conn: Connection) -> 'DownloadSpeed': ...


class Ping(BaseRequest, type_id=0xFF, struct=Struct('>Q')):
    data: PingData

    @classmethod
    async def recv_from_conn(cls, conn) -> 'Ping': ...
