from asyncio import BaseEventLoop, Future, Task, get_event_loop
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional, Tuple

from sentry_sdk import Scope
from tornado.iostream import IOStream

from cats.headers import T_Headers
from cats.identity import Identity
from cats.server.app import Application
from cats.server.handlers import HandlerFunc
from cats.server.request import BaseRequest, Input, InputRequest, Request
from cats.typing import BytesAnyGen


class Connection:
    MAX_PLAIN_DATA_SIZE: int

    __slots__ = (
        '_closed', 'stream', 'host', 'port', 'api_version', '_app', '_scope', 'download_speed',
        '_identity', '_credentials', 'loop', 'input_deq', '_idle_timer', '_message_pool', 'is_sending',
    )

    def __init__(self, stream: IOStream, address: Tuple[str, int], api_version: int, app: Application):
        self._closed: bool = False
        self.stream: IOStream
        self.host: str = address[0]
        self.port: int = address[1]
        self.api_version: int = api_version
        self._app: Application = app
        self._scope: Scope = Scope()
        self._identity: Optional[Identity] = None
        self._credentials: Any = None
        self.loop: BaseEventLoop = get_event_loop()
        self.input_deq: Dict[int, Input] = {}
        self._idle_timer: Optional[Future] = None
        self._message_pool: List[int] = []
        self.is_sending: bool = False
        self.download_speed: int = 0

    @property
    def is_open(self) -> bool: ...

    @property
    def app(self) -> Application: ...

    async def init(self) -> None: ...

    async def start(self, ping: bool = True) -> None: ...

    async def ping(self) -> None: ...

    async def set_download_speed(self, speed: int = 0): ...

    async def send(self, handler_id: int, data: Any, message_id: int = None, compression: int = None, *,
                   headers: T_Headers = None, status: int = 200) -> None: ...

    async def send_stream(self, handler_id: int, data: BytesAnyGen, data_type: int,
                          message_id: int = None, compression: int = None, *,
                          headers: T_Headers = None, status: int = 200) -> None: ...

    def on_tick_done(self, task: Task): ...

    def attach_to_channel(self, channel: str): ...

    def detach_from_channel(self, channel: str): ...

    async def tick(self, request: BaseRequest) -> None: ...

    @property
    def identity(self) -> Optional[Identity]: ...

    @property
    def credentials(self) -> Optional[Any]: ...

    @property
    def identity_scope_user(self): ...

    def signed_in(self) -> bool: ...

    def sign_in(self, identity: Identity, credentials: Any = None): ...

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

    @asynccontextmanager
    async def lock_write(self): ...
