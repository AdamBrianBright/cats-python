from asyncio import CancelledError, Future, Task, get_event_loop, shield
from functools import partial
from logging import getLogger
from random import randint
from typing import Any, AsyncIterable, Dict, Iterable, List, Optional, Tuple, Union

from tornado.iostream import IOStream, StreamClosedError

from cats.events import Event
from cats.handlers import HandlerFunc
from cats.request import BaseRequest, InputRequest, Request, StreamRequest

__all__ = [
    'Connection',
]

logging = getLogger('CATS.Connection')


class Connection:
    MAX_PLAIN_DATA_SIZE: int = 1 << 24

    __slots__ = (
        '_closed', 'stream', 'host', 'port', 'api_version', 'server',
        'loop', 'input_queue', '_idle_timer', '_message_pool', 'is_sending',
    )

    def __init__(self, stream: IOStream, address: Tuple[str, int], api_version: int, server):
        logging.debug(f'New connection established: {address}')
        self._closed: bool = False
        self.stream = stream
        self.host, self.port = address
        self.api_version = api_version
        self.server = server
        self.loop = get_event_loop()
        self.input_queue: Dict[int, Future] = {}
        self._idle_timer: Optional[Future] = None
        self._message_pool: List[int] = []
        self.is_sending: bool = False

    @property
    def is_open(self):
        return not self.stream.closed() and self.server.is_running

    @property
    def app(self):
        return self.server.app

    async def init(self):
        await self.app.trigger(Event.ON_CONN_START, conn=self)
        logging.debug(f'{self} initialized')

    async def start(self):
        while self.is_open:
            request = await self.recv()
            task: Task = self.loop.create_task(self.tick(request))
            task.add_done_callback(self.on_tick_done)

    async def send(self, handler_id: int, data: Any, message_id: int = None, status: int = None):
        if message_id is None:
            message_id = self._get_free_message_id()
        request = Request(conn=self, message_id=message_id, data=data, handler_id=handler_id, status=status)
        await request.send_to_conn()

    async def send_stream(self, handler_id: int, data: Union[AsyncIterable[bytes], Iterable[bytes]], data_type: int,
                          message_id: int = None, status: int = None):
        if message_id is None:
            message_id = self._get_free_message_id()
        request = StreamRequest(conn=self, message_id=message_id,
                                data=data, data_type=data_type,
                                handler_id=handler_id, status=status)
        await request.send_to_conn()

    async def tick(self, request: BaseRequest):
        if isinstance(request, Request):
            await self.handle_request(request)
        elif isinstance(request, InputRequest):
            await self.handle_input_answer(request)
        else:
            raise self.ProtocolError('Unsupported request')

    def on_tick_done(self, task: Task):
        if exc := task.exception():
            self.loop.create_task(self.close(exc))

    async def handle_input_answer(self, request):
        fut: Future = self.input_queue.pop(request.message_id, None)
        if fut is None:
            raise self.ProtocolError('Received answer but input does`t exists')
        fut.set_result(request)
        fut.done()

    async def handle_request(self, request):
        message_id = request.message_id

        if message_id in self._message_pool:
            raise self.ProtocolError('Provided message_id already in use')
        fn = await self.dispatch(request)
        for middleware in self.app.middleware:
            fn = partial(middleware, fn)

        self._message_pool.append(message_id)
        try:
            result = await shield(fn(request))
            if result is not None:
                if isinstance(result, tuple) and len(result) == 2:
                    result, status = result
                else:
                    status = 200
                response = Request(self, request.message_id, result, request.handler_id, status=status)
                await response.send_to_conn()
        except (KeyboardInterrupt, CancelledError, StreamClosedError):
            raise
        except Exception as err:
            await self.app.trigger(Event.ON_HANDLE_ERROR, request=request, exc=err)
        self._message_pool.remove(message_id)

    async def recv(self):
        self.reset_idle_timer()
        message_type: int = int.from_bytes(await self.stream.read_bytes(1), 'big', signed=False)
        request_class = BaseRequest.get_class_by_type_id(message_type)
        if request_class is None:
            raise self.ProtocolError('Received unknown message type [first byte]')

        return await request_class.recv_from_conn(self)

    async def dispatch(self, request: Request) -> HandlerFunc:
        handlers = self.app.get_handlers_by_id(request.handler_id)
        if not handlers:
            raise request.conn.ProtocolError(f'Handler with id {request.handler_id} not found')

        if isinstance(handlers, list):
            for item in handlers:
                end_version = request.conn.api_version if item.end_version is None else item.end_version
                if item.version <= request.conn.api_version <= end_version:
                    fn = item.callback
                    break
            else:
                raise request.conn.ProtocolError(f'Handler with id {request.handler_id} not found')
        else:
            fn = handlers.callback

        return fn

    async def close(self, exc: Exception = None):
        if self._closed:
            return
        self._closed = True
        if self._idle_timer is not None:
            self._idle_timer.cancel()
            self._idle_timer = None
        await self.app.trigger(Event.ON_CONN_CLOSE, conn=self, exc=exc)
        self.stream.close(exc)
        logging.debug(f'{self} closed: {exc = }')

    def _close(self, exc: Exception = None):
        self.loop.create_task(self.close(exc))

    def __str__(self) -> str:
        return f'CATS.Connection: {self.host}:{self.port} api@{self.api_version}'

    class ProtocolError(ValueError, IOError):
        pass

    def reset_idle_timer(self):
        if self.server.idle_timeout > 0:
            if self._idle_timer is not None:
                self._idle_timer.cancel()

            self._idle_timer = self.loop.call_later(self.server.idle_timeout, partial(self._close, TimeoutError))

    def _get_free_message_id(self) -> int:
        while True:
            message_id = randint(17783, 35565)
            if message_id not in self._message_pool:
                break

        return message_id
