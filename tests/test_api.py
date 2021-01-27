import asyncio
import os

from pytest import mark, raises
from tornado.iostream import IOStream, StreamClosedError

from cats import Connection, InputRequest, Request, StreamRequest
from tests.utils import init_cats_conn


@mark.asyncio
async def test_echo_handler(cats_conn: Connection):
    payload = os.urandom(10)
    await cats_conn.send(0, payload)
    response = await cats_conn.recv()
    assert response.data == payload


@mark.asyncio
async def test_no_response(cats_conn: Connection):
    payload = os.urandom(10)
    await cats_conn.send(1, payload)
    with raises(asyncio.TimeoutError):
        await asyncio.wait_for(cats_conn.recv(), 0.2)


@mark.parametrize('api_version, handler_version', [
    [0, None],
    [1, 1],
    [2, 1],
    [3, 2],
    [4, 2],
    [5, None],
    [6, 3],
    [7, 3],
])
@mark.asyncio
async def test_api_version(cats_client_stream: IOStream, cats_server, api_version: int, handler_version: int):
    conn = await init_cats_conn(cats_client_stream, '127.0.0.1', cats_server.port, cats_server, api_version)
    await conn.send(2, b'')

    if handler_version is not None:
        response = await conn.recv()
        assert response.data == {'version': handler_version}
    else:
        with raises(StreamClosedError):
            await conn.recv()


@mark.asyncio
async def test_api_stream(cats_conn: Connection):
    await cats_conn.send(0xFFFF, None)
    result = await cats_conn.recv()
    assert isinstance(result, StreamRequest)
    assert result.data == b'hello world!'


@mark.parametrize('answer, result', [
    [b'yes', b'Nice!'],
    [b'no', b'Sad!'],
])
@mark.asyncio
async def test_api_internal_request(cats_conn: Connection, answer, result):
    await cats_conn.send(0xFFA0, None)
    response = await cats_conn.recv()
    assert isinstance(response, InputRequest)
    assert response.data == b'Are you ok?'
    await response.answer(answer)
    response = await cats_conn.recv()
    assert isinstance(response, Request)
    assert response.data == result


@mark.parametrize('answer, result', [
    ['yes', 'Nice!'],
    ['no', 'Sad!'],
])
@mark.asyncio
async def test_api_internal_json_request(cats_conn: Connection, answer, result):
    await cats_conn.send(0xFFA1, None)
    response = await cats_conn.recv()
    assert isinstance(response, InputRequest)
    assert response.data == 'Are you ok?'
    await response.answer(answer)
    response = await cats_conn.recv()
    assert isinstance(response, Request)
    assert response.data == result
