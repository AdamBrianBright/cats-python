from asyncio import CancelledError, Future, Task, get_event_loop, shield, sleep
from contextlib import asynccontextmanager
from functools import partial
from logging import getLogger
from random import randint
from typing import Any, Dict, Iterable, List, Optional, Tuple, Union

from sentry_sdk import Scope, add_breadcrumb, capture_exception
from tornado.iostream import IOStream, StreamClosedError

from cats.errors import ProtocolError
from cats.events import Event
from cats.handshake import HandshakeError
from cats.headers import Headers
from cats.identity import Identity
from cats.server.handlers import HandlerFunc
from cats.server.request import BaseRequest, InputRequest, Request
from cats.server.response import Response, StreamResponse
from cats.typing import BytesAnyGen

__all__ = [
    'Connection',
]

logging = getLogger('CATS.Connection')


class Connection:
    MAX_PLAIN_DATA_SIZE: int = 1 << 24

    __slots__ = (
        '_closed', 'stream', 'host', 'port', 'api_version', '_app', '_scope', 'download_speed',
        '_identity', '_credentials', 'loop', 'input_queue', '_idle_timer', '_message_pool', 'is_sending',
    )

    def __init__(self, stream: IOStream, address: Tuple[str, int], api_version: int, app):
        logging.debug(f'New connection established: {address}')
        self._closed: bool = False
        self.stream = stream
        self.host, self.port = address
        self.api_version = api_version
        self._app = app
        self._scope = Scope()
        self._identity: Optional[Identity] = None
        self._credentials: Any = None
        self.loop = get_event_loop()
        self.input_queue: Dict[int, Future] = {}
        self._idle_timer: Optional[Future] = None
        self._message_pool: List[int] = []
        self.is_sending: bool = False
        self.download_speed: int = 0

    @property
    def is_open(self):
        return not self._closed and not self.stream.closed()

    @property
    def app(self):
        return self._app

    async def init(self):
        logging.debug(f'{self} initialized')

    async def start(self):
        while self.is_open:
            request = await self.recv()
            task: Task = self.loop.create_task(self.tick(request))
            task.add_done_callback(self.on_tick_done)

    async def set_download_speed(self, speed: int = 0):
        await self.stream.write(b'\x05')
        await self.stream.write(speed.to_bytes(4, 'big', signed=False))

    async def send(self, handler_id: int, data: Any = None, headers: Union[Dict[str, Any], Headers] = None,
                   message_id: int = None, status: int = None, compression: int = None):
        response = Response(data=data, headers=headers, status=status, compression=compression)
        response.handler_id = handler_id
        response.message_id = self._get_free_message_id() if message_id is None else message_id
        await response.send_to_conn(self)

    async def send_stream(self, handler_id: int, data: BytesAnyGen, data_type: int,
                          headers: Union[Dict[str, Any], Headers] = None,
                          message_id: int = None, status: int = None, compression: int = None):
        response = StreamResponse(data=data, headers=headers, status=status,
                                  compression=compression, data_type=data_type)
        response.handler_id = handler_id
        response.message_id = self._get_free_message_id() if message_id is None else message_id
        await response.send_to_conn(self)

    def attach_to_channel(self, channel: str):
        self.app.attach_conn_to_channel(self, channel=channel)

    def detach_from_channel(self, channel: str):
        self.app.detach_conn_from_channel(self, channel=channel)

    @property
    def conns_with_same_identity(self) -> Iterable['Connection']:
        return self.app.channel(f'model_{self._identity.model_name}:{self._identity.id}')

    @property
    def conns_with_same_model(self) -> Iterable['Connection']:
        return self.app.channel(f'model_{self._identity.model_name}')

    async def tick(self, request: BaseRequest):
        if request.type_id == 5:
            limit = request.data
            if not limit or 1024 <= limit <= 33_554_432:
                self.download_speed = limit
            else:
                logging.error('Unsupported download speed limit')
        elif isinstance(request, Request):
            await self.handle_request(request)
        elif isinstance(request, InputRequest):
            await self.handle_input_answer(request)
        else:
            raise ProtocolError('Unsupported request')

    @property
    def identity(self) -> Optional[Identity]:
        return self._identity

    @property
    def credentials(self) -> Optional[Any]:
        return self._credentials

    @property
    def identity_scope_user(self):
        if not self.signed_in():
            return {'ip': self.host}

        return self.identity.sentry_scope

    def signed_in(self) -> bool:
        return self._identity is not None

    def sign_in(self, identity: Identity, credentials: Any = None):
        self._identity: Optional[Identity] = identity
        self._credentials = credentials

        model_group = f'model_{identity.model_name}'
        auth_group = f'{model_group}:{identity.id}'
        self.attach_to_channel(model_group)
        self.attach_to_channel(auth_group)

        self._scope.set_user(self.identity_scope_user)
        add_breadcrumb(message='Sign in', data={
            'id': identity.id,
            'model': identity.__class__.__name__,
            'instance': repr(identity),
        })

        logging.debug(f'Signed in as {identity.__class__.__name__} <{self.host}:{self.port}>')

    def sign_out(self):
        logging.debug(f'Signed out from {self.identity.__class__.__name__} <{self.host}:{self.port}>')
        if self.signed_in():
            model_group = f'model_{self.identity.model_name}'
            auth_group = f'{model_group}:{self._identity.id}'

            self.detach_from_channel(auth_group)
            self.detach_from_channel(model_group)

            self._identity = None
            self._credentials = None

        self._scope.set_user(self.identity_scope_user)
        add_breadcrumb(message='Sign out')

        return self

    def on_tick_done(self, task: Task):
        if exc := task.exception():
            self.close(exc)

    async def handle_input_answer(self, request):
        fut: Future = self.input_queue.pop(request.message_id, None)
        if fut is None:
            raise ProtocolError('Received answer but input does`t exists')
        fut.set_result(request)
        fut.done()

    async def handle_request(self, request):
        message_id = request.message_id

        if message_id in self._message_pool:
            raise ProtocolError('Provided message_id already in use')
        fn = await self.dispatch(request)
        for middleware in self.app.middleware:
            fn = partial(middleware, fn)

        self._message_pool.append(message_id)
        try:
            result = await shield(fn(request))
            if result is not None:
                if not isinstance(result, (Response, StreamResponse)):
                    raise ProtocolError('Returned invalid response')

                result.handler_id = request.handler_id
                result.message_id = request.message_id
                result.offset = request.headers.get('Offset', 0)
                await result.send_to_conn(self)
        except (KeyboardInterrupt, CancelledError, StreamClosedError):
            raise
        except Exception as err:
            capture_exception(err, scope=self._scope)
            await self.app.trigger(Event.ON_HANDLE_ERROR, request=request, exc=err)
        self._message_pool.remove(message_id)

    async def recv(self):
        self.reset_idle_timer()
        message_type: int = int.from_bytes(await self.stream.read_bytes(1), 'big', signed=False)
        request_class = BaseRequest.get_class_by_type_id(message_type)
        if request_class is None:
            raise ProtocolError(f'Received unknown message type [first byte = {hex(message_type)[2:]}]')

        return await request_class.recv_from_conn(self)

    async def dispatch(self, request: Request) -> HandlerFunc:
        handlers = self.app.get_handlers_by_id(request.handler_id)
        if not handlers:
            raise ProtocolError(f'Handler with id {request.handler_id} not found')

        if isinstance(handlers, list):
            for item in handlers:
                end_version = request.conn.api_version if item.end_version is None else item.end_version
                if item.version <= request.conn.api_version <= end_version:
                    fn = item.callback
                    break
            else:
                raise ProtocolError(f'Handler with id {request.handler_id} not found')
        else:
            fn = handlers.callback

        return fn

    def close(self, exc: Exception = None):
        if self._closed:
            return

        self._closed = True

        self.sign_out()
        if exc and not isinstance(exc, (HandshakeError,)):
            logging.error(f'Connection {(self.host, self.port)} closed')
            logging.error(exc)
            capture_exception(exc, scope=self._scope)

        if self._idle_timer is not None:
            self._idle_timer.cancel()
            self._idle_timer = None
        self.stream.close(exc)
        logging.debug(f'{self} closed: {exc = }', exc_info=exc)

    def __str__(self) -> str:
        return f'CATS.Connection: {self.host}:{self.port} api@{self.api_version}'

    def reset_idle_timer(self):
        if self.app.idle_timeout > 0:
            if self._idle_timer is not None:
                self._idle_timer.cancel()

            self._idle_timer = self.loop.call_later(self.app.idle_timeout, partial(self.close, TimeoutError))

    def _get_free_message_id(self) -> int:
        while True:
            message_id = randint(17783, 35565)
            if message_id not in self._message_pool:
                break

        return message_id

    @asynccontextmanager
    async def lock_write(self):
        while self.is_sending:
            await sleep(0.05)
        self.is_sending = True
        yield
        self.is_sending = False
