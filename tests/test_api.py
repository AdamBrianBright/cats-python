import asyncio
import os
from datetime import datetime

from pytest import mark, raises
from tornado.iostream import IOStream, StreamClosedError

from cats.codecs import FileInfo
from cats.server import Connection, InputRequest, Request, StreamRequest
from cats.utils import tmp_file
from tests.utils import init_cats_conn


@mark.asyncio
async def test_echo_handler(cats_conn: Connection):
    payload = os.urandom(10)
    await cats_conn.send(0, payload)
    response = await cats_conn.recv()
    assert response.data == payload


@mark.asyncio
async def test_echo_handler_files(cats_conn: Connection):
    payload = tmp_file()
    await cats_conn.send(0, payload)
    response = await cats_conn.recv()
    assert isinstance(response.data, dict)
    for key, val in response.data.items():
        assert isinstance(key, str)
        assert isinstance(val, FileInfo)


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
    conn = await init_cats_conn(cats_client_stream, '127.0.0.1',
                                cats_server.port, cats_server.app,
                                api_version, cats_server.handshake)
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


@mark.asyncio
async def test_api_json_validation(cats_conn: Connection):
    await cats_conn.send(0xFFB0, {'id': 5, 'name': 'adam'})
    response = await cats_conn.recv()
    assert isinstance(response, Request)

    data = response.data
    assert isinstance(data, dict)
    assert isinstance(data['token'], str) and len(data['token']) == 64
    assert isinstance(data['code'], str) and len(data['code']) == 6


@mark.asyncio
async def test_api_json_invalid(cats_conn: Connection):
    await cats_conn.send(0xFFB0, 'not even a dict')
    res = await cats_conn.recv()
    assert isinstance(res, Request)
    assert res.status == 500


@mark.asyncio
async def test_api_speed_limiter(cats_conn: Connection):
    payload = os.urandom(100_000)

    await cats_conn.send(0x0000, payload)
    start = datetime.now()
    res = await cats_conn.recv()
    assert 0 <= (datetime.now() - start).total_seconds() <= 0.1
    assert res.data == payload

    await cats_conn.set_download_speed(50_000)

    await cats_conn.send(0x0000, payload)
    start = datetime.now()
    res = await cats_conn.recv()
    assert 1 <= (datetime.now() - start).total_seconds() <= 2
    assert res.data == payload


@mark.asyncio
async def test_api_payload_offset(cats_conn: Connection):
    payload = os.urandom(10)
    await cats_conn.send(0, payload, headers={"Offset": 5})
    response = await cats_conn.recv()
    assert response.data == payload[5:]


@mark.asyncio
async def test_api_payload_offset_files(cats_conn: Connection):
    payload = tmp_file()
    with payload.open('wb') as fh:
        fh.write(b'1234567890')

    await cats_conn.send(0, payload, headers={"Offset": 5})
    response = await cats_conn.recv()
    assert isinstance(response.data, dict)
    for key, val in response.data.items():
        assert isinstance(key, str)
        assert isinstance(val, FileInfo)
        assert val.size == 5
        assert val.path.read_bytes() == b'67890'


@mark.asyncio
async def test_cancel_input(cats_conn: Connection):
    await cats_conn.send(0xFFA0, None)
    response = await cats_conn.recv()
    assert isinstance(response, InputRequest)
    assert response.data == b'Are you ok?'
    await response.cancel()
    response = await cats_conn.recv()
    assert isinstance(response, Request)
    assert response.status == 500, response.data
