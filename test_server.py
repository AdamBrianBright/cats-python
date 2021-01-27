import logging
from asyncio import sleep

from tornado.ioloop import IOLoop
from tornado.iostream import IOStream

from cats import Api, Application, Handler, Request, SHA256TimeHandshake, Server
from cats.codecs import Codec
from cats.middleware import default_error_handler

logging.basicConfig(level='DEBUG', force=True)

rb = IOStream.read_bytes
wr = IOStream.write


async def read_bytes(self, num_bytes, partial: bool = False):
    print(f'Reading {num_bytes} {partial = }')
    chunk = await rb(self, num_bytes, partial=partial)
    print(f'Got {chunk = }')
    return chunk


async def write(self, data):
    print(f'Sending {data = }')
    return await wr(self, data)


IOStream.read_bytes = read_bytes
IOStream.write = write

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
        yield b'world'
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


def main():
    app = Application([api], [default_error_handler])
    handshake = SHA256TimeHandshake(b'secret_key', 1)
    server = Server(app, handshake=handshake, idle_timeout=5.0, input_timeout=1.0)
    server.bind(9095, '0.0.0.0')
    server.start(1)
    IOLoop.current().start()
    print('Starting CATS at 0.0.0.0:9095')


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('\nDone')
