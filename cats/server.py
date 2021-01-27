import socket
import ssl
from asyncio import CancelledError, get_event_loop, run
from datetime import datetime, timezone
from logging import getLogger
from typing import Any, Dict, List, Optional, Tuple, Union

from tornado.iostream import IOStream
from tornado.tcpserver import TCPServer
from tornado.testing import bind_unused_port

from cats.app import Application
from cats.conn import Connection
from cats.events import Event
from cats.handshake import Handshake

__all__ = [
    'Server',
]

logging = getLogger('CATS.Server')


class Server(TCPServer):

    def __init__(self, app: Application, handshake: Handshake = None,
                 idle_timeout: Union[int, float] = None, input_timeout: Union[int, float] = None,
                 ssl_options: Optional[Union[Dict[str, Any], ssl.SSLContext]] = None,
                 max_buffer_size: Optional[int] = None, read_chunk_size: Optional[int] = None) -> None:
        self.app = app
        self.handshake = handshake
        self.port: Optional[int] = None
        self.idle_timeout = idle_timeout or 0
        self.input_timeout = input_timeout or 0
        self.connections: List[Connection] = []
        super().__init__(ssl_options, max_buffer_size, read_chunk_size)

    # TCP Connection entry point
    async def handle_stream(self, stream: IOStream, address: Tuple[str, int]) -> None:
        conn = await self.init_connection(stream, address)
        self.app.attach_conn_to_channel(conn, '__all__')
        self.connections.append(conn)
        try:
            await conn.start()
        except (KeyboardInterrupt, CancelledError):
            raise
        except Exception as err:
            await conn.close(exc=err)
            stream.close(err)
        finally:
            self.app.remove_conn_from_channels(conn)
            self.connections.remove(conn)

    async def init_connection(self, stream: IOStream, address: Tuple[str, int]) -> Connection:
        api_version = int.from_bytes(await stream.read_bytes(4), 'big', signed=False)

        current_time = datetime.now(tz=timezone.utc).timestamp()
        await stream.write(round(current_time * 1000).to_bytes(8, 'big', signed=False))

        conn = Connection(stream, address, api_version, self)
        if self.handshake is not None:
            await self.handshake.validate(conn)

        await conn.init()
        return conn

    @property
    def is_running(self) -> bool:
        return self._started and not self._stopped

    def shutdown(self, exc=None):
        event = self.app.trigger(Event.ON_SERVER_SHUTDOWN, server=self, exc=exc)
        loop = get_event_loop()
        if loop and loop.is_running() and not loop.is_closed():
            loop.create_task(event)
            for conn in self.connections:
                loop.create_task(conn.close(exc))
        else:
            run(event)
            for conn in self.connections:
                run(conn.close(exc))

        self.app.clear_all_channels()
        self.connections.clear()
        logging.info('Shutting down TCP Server')
        self.stop()

    def start(self, num_processes: Optional[int] = 1, max_restarts: Optional[int] = None) -> None:
        super().start(num_processes, max_restarts)
        get_event_loop().create_task(self.app.trigger(Event.ON_SERVER_START, server=self))

    def bind_unused_port(self):
        sock, port = bind_unused_port()
        self.add_socket(sock)
        self.port = port

    def bind(self, port: int, address: Optional[str] = None, family: socket.AddressFamily = socket.AF_UNSPEC,
             backlog: int = 128, reuse_port: bool = False) -> None:
        super().bind(port, address, family, backlog, reuse_port)
        self.port = port

    def listen(self, port: int, address: str = "") -> None:
        super().listen(port, address)
        self.port = port