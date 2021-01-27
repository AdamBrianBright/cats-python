import asyncio
import platform
from typing import List

from pytest import fixture, mark
from tornado.iostream import IOStream
from tornado.tcpclient import TCPClient

import cats
import cats.middleware
from tests.utils import init_cats_conn


# import logging
#
# logging.basicConfig(level='DEBUG', force=True)
#
# rb = IOStream.read_bytes
# wr = IOStream.write
#
#
# async def read_bytes(self, num_bytes, partial: bool = False):
#     print(f'Reading {num_bytes} {partial = }')
#     chunk = await rb(self, num_bytes, partial=partial)
#     print(f'Got {chunk = }')
#     return chunk
#
#
# async def write(self, data):
#     print(f'Sending {data = }')
#     return await wr(self, data)
#
#
# IOStream.read_bytes = read_bytes
# IOStream.write = write


@fixture(scope='session')
def event_loop():
    if platform.system() == 'Windows':
        # noinspection PyUnresolvedReferences
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    return asyncio.get_event_loop()


@fixture(scope='session')
def cats_api_list() -> List[cats.Api]:
    from tests.handlers import api
    return [
        api,
    ]


@fixture(scope='session')
def cats_middleware() -> List[cats.middleware.Middleware]:
    return [
        cats.middleware.default_error_handler,
    ]


@fixture(scope='session')
def cats_app(cats_api_list, cats_middleware) -> cats.Application:
    app = cats.Application(cats_api_list, cats_middleware)
    return app


@fixture(scope='session')
def cats_handshake() -> cats.Handshake:
    return cats.SHA256TimeHandshake(b'secret_key', 1)


@fixture(scope='session')
def cats_server(cats_app, cats_handshake) -> cats.Server:
    cats_server = cats.Server(app=cats_app, handshake=cats_handshake)
    cats_server.bind_unused_port()
    cats_server.start(1)
    yield cats_server
    cats_server.shutdown()


@fixture
@mark.asyncio
async def cats_client_stream(cats_server) -> IOStream:
    tcp_client = TCPClient()
    stream = await tcp_client.connect('127.0.0.1', cats_server.port)
    yield stream
    stream.close()


@fixture
@mark.asyncio
async def cats_conn(cats_client_stream, cats_server) -> cats.Connection:
    conn = await init_cats_conn(cats_client_stream, '127.0.0.1', cats_server.port, cats_server, 1)
    yield conn
    await conn.close()