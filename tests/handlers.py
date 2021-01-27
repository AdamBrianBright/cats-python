from asyncio import sleep

from cats import Api, Handler, Request
from cats.codecs import Codec

api = Api()


@api.on(0, name='echo handler')
async def echo_handler(request: Request):
    print('ECHO HANDLER issued')
    return request.data


@api.on(1, name='no response')
async def no_response(request: Request):
    return None


class VersionedHandler(Handler, api=api, id=2, version=1):
    async def handle(self):
        return {'version': 1}


class VersionedHandler2(Handler, api=api, id=2, version=3, end_version=4):
    async def handle(self):
        return {'version': 2}


class VersionedHandler3(Handler, api=api, id=2, version=6):
    async def handle(self):
        return {'version': 3}


@api.on(id=0xFFFF, name='delayed response')
async def delayed_response(request: Request):
    async def gen():
        yield b'hello'
        await sleep(0.5)
        yield b' world'
        await sleep(0.5)
        yield b'!'

    await request.conn.send_stream(request.handler_id, gen(), data_type=Codec.T_BYTE)


@api.on(id=0xFFA0, name='internal requests')
async def internal_requests(request: Request):
    res = await request.input(b'Are you ok?')
    if res.data == b'yes':
        return b'Nice!'
    else:
        return b'Sad!'


@api.on(id=0xFFA1, name='internal requests')
async def internal_json_requests(request: Request):
    res = await request.input("Are you ok?")
    if res.data == "yes":
        return "Nice!"
    else:
        return "Sad!"
