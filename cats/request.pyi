from datetime import datetime, timezone
from struct import Struct
from typing import Any, AsyncIterable, Dict, Optional, Tuple, Type, Union

from cats import Connection
from cats.codecs import Files


class BaseRequest(dict):
    __slots__ = ('conn', 'message_id', 'data')
    __registry__: Dict[int, Type['BaseRequest']] = {}
    type_id: int
    struct: Struct

    def __init__(self, conn: Connection, message_id: int, data: Any):
        super().__init__()
        self.conn: Connection = conn
        self.message_id: int = message_id
        self.data: Any = data

    def __new__(cls, *args, **kwargs): ...

    def __init_subclass__(cls, /, type_id: int, struct: Struct): ...

    @classmethod
    def get_class_by_type_id(cls, message_type: int) -> Optional[Type['BaseRequest']]: ...

    async def input(self, data: Any) -> 'InputRequest': ...

    @classmethod
    async def recv_from_conn(cls, conn) -> 'BaseRequest': ...

    async def send_to_conn(self) -> None: ...


class Request(BaseRequest, type_id=0x00, struct=Struct('>HHHQBBI')):
    __slots__ = ('handler_id', 'status', 'send_time')

    def __init__(self, conn, message_id: int, data: Any, handler_id: int, data_type: int = None,
                 status: int = 200, send_time: datetime = None):
        self.handler_id: int = handler_id
        self.status: int = status
        self.send_time: datetime = send_time or datetime.now(timezone.utc)
        self.data_type: Optional[int] = data_type
        super().__init__(conn, message_id, data)

    @classmethod
    async def recv_from_conn(cls, conn) -> 'Request': ...

    @classmethod
    async def recv_data(cls, conn, data_type: int, data_len: int, compression: int) -> Union[Files, Any]: ...

    async def send_to_conn(self) -> None: ...


class StreamRequest(Request, type_id=0x01, struct=Struct('>HHHQBB')):
    __slots__ = ('data_type', 'handler_id', 'status', 'send_time')

    def __init__(self, conn, message_id: int, data: Any, handler_id: int, data_type: int,
                 status: int = 200, send_time: datetime = None):
        super().__init__(conn, message_id, data, handler_id, data_type, status, send_time)
        self.data_type: int

    @classmethod
    async def recv_from_conn(cls, conn) -> 'StreamRequest': ...

    @classmethod
    async def recv_data(cls, conn, data_type: int, compression: int, **kwargs) -> Tuple[Union[Files, Any], int]: ...

    async def _async_gen(self, gen) -> AsyncIterable: ...

    async def send_to_conn(self) -> None: ...


class InputRequest(BaseRequest, type_id=0x02, struct=Struct('>HBBI')):

    @classmethod
    async def recv_from_conn(cls, conn) -> 'InputRequest': ...

    async def send_to_conn(self) -> None: ...

    async def answer(self, data) -> None: ...
