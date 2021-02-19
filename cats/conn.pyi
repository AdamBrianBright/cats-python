from asyncio import BaseEventLoop, Future, Task
from typing import Any, AsyncIterable, Dict, Iterable, List, Optional, Tuple, Union

from sentry_sdk import Scope
from tornado.iostream import IOStream

from cats import Application, BaseRequest, HandlerFunc, Headers, Identity, InputRequest, Request


class Connection:
    MAX_PLAIN_DATA_SIZE: int

    __slots__ = (
        '_closed', 'stream', 'host', 'port', 'api_version', '_app', '_scope', 'download_speed',
        '_identity', 'loop', 'input_queue', '_idle_timer', '_message_pool', 'is_sending',
    )

    def __init__(self, stream: IOStream, address: Tuple[str, int], api_version: int, app: Application):
        self._closed: bool
        self.stream: IOStream
        self.host: str
        self.port: int
        self.api_version: int
        self._app: Application
        self._scope: Scope
        self._identity: None
        self.loop: BaseEventLoop
        self.input_queue: Dict[int, Future]
        self._idle_timer: Optional[Future]
        self._message_pool: List[int]
        self.is_sending: bool
        self.download_speed: int

    @property
    def is_open(self) -> bool: ...

    @property
    def app(self) -> Application: ...

    async def init(self) -> None: ...

    async def start(self) -> None: ...

    async def set_download_speed(self, speed: int = 0): ...

    async def send(self, handler_id: int, data: Any, headers: Headers = None,
                   message_id: int = None, status: int = None) -> None: ...

    async def send_stream(self, handler_id: int, data: Union[AsyncIterable[bytes], Iterable[bytes]], data_type: int,
                          headers: Headers = None, message_id: int = None, status: int = None) -> None: ...

    def on_tick_done(self, task: Task): ...

    def attach_to_channel(self, channel: str): ...

    def detach_from_channel(self, channel: str): ...

    async def tick(self, request: BaseRequest) -> None: ...

    @property
    def identity(self) -> Optional[Identity]: ...

    @property
    def identity_scope_user(self): ...

    def signed_in(self) -> bool: ...

    def sign_in(self, identity: Any): ...

    def sign_out(self): ...

    async def handle_input_answer(self, request: InputRequest): ...

    async def handle_request(self, request: Request): ...

    async def recv(self) -> BaseRequest: ...

    async def dispatch(self, request: Request) -> HandlerFunc: ...

    def close(self, exc: Exception = None) -> None: ...

    def __str__(self) -> str: ...

    class ProtocolError(ValueError, IOError):
        pass

    def reset_idle_timer(self) -> None: ...

    def _get_free_message_id(self) -> int: ...
