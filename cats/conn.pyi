from asyncio import BaseEventLoop, Future, Task
from typing import Any, AsyncIterable, Dict, Iterable, List, Optional, Tuple, Union

from tornado.iostream import IOStream

from cats import Application, BaseRequest, HandlerFunc, InputRequest, Request, Server


class Connection:
    MAX_PLAIN_DATA_SIZE: int

    __slots__ = (
        '_closed', 'stream', 'host', 'port', 'api_version', 'server',
        'loop', 'input_queue', '_idle_timer', '_message_pool',
    )

    def __init__(self, stream: IOStream, address: Tuple[str, int], api_version: int, server: Server):
        self._closed: bool
        self.stream: IOStream
        self.host: str
        self.port: int
        self.api_version: int
        self.server: Server
        self.loop: BaseEventLoop
        self.input_queue: Dict[int, Future]
        self._idle_timer: Optional[Future]
        self._message_pool: List[int]

    @property
    def is_open(self) -> bool: ...

    @property
    def app(self) -> Application: ...

    async def init(self) -> None: ...

    async def start(self) -> None: ...

    async def send(self, handler_id: int, data: Any, message_id: int = None, status: int = None) -> None: ...

    async def send_stream(self, handler_id: int, data: Union[AsyncIterable[bytes], Iterable[bytes]], data_type: int,
                          message_id: int = None, status: int = None) -> None: ...

    def on_tick_done(self, task: Task): ...

    async def tick(self, request: BaseRequest) -> None: ...

    async def handle_input_answer(self, request: InputRequest): ...

    async def handle_request(self, request: Request): ...

    async def recv(self) -> BaseRequest: ...

    async def dispatch(self, request: Request) -> HandlerFunc: ...

    async def close(self, exc: Exception = None) -> None: ...

    def _close(self, exc: Exception = None) -> None: ...

    def __str__(self) -> str: ...

    class ProtocolError(ValueError, IOError):
        pass

    def reset_idle_timer(self) -> None: ...

    def _get_free_message_id(self) -> int: ...
