import logging
from asyncio import run

from tornado.iostream import IOStream
from tornado.tcpclient import TCPClient

from cats import Application, Connection, SHA256TimeHandshake, Server

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

handshake = SHA256TimeHandshake(b'secret_key', time_window=1)
server = Server(Application([]), handshake=handshake)


async def gen_conn(api_version: int) -> Connection:
    client = TCPClient()
    stream = await client.connect('127.0.0.1', 9095)
    await stream.write(api_version.to_bytes(4, 'big', signed=False))
    await stream.read_bytes(8)
    await stream.write(handshake.get_hashes()[0].encode('utf-8'))
    return Connection(stream, ('127.0.0.1', 9095), api_version, server)


async def main():
    conn = await gen_conn(1)
    await conn.send(0, b'Hello world')
    print(await conn.recv())


if __name__ == '__main__':
    run(main())
