from tornado.iostream import IOStream

from cats import SHA256TimeHandshake
from cats.server import Application, Connection

__all__ = [
    'init_cats_conn',
]


async def init_cats_conn(stream: IOStream, host: str, port: int, app: Application,
                         api_version: int = 1, handshake: SHA256TimeHandshake = None) -> Connection:
    await stream.write(api_version.to_bytes(4, 'big', signed=False))
    await stream.read_bytes(8)
    await stream.write(handshake.get_hashes()[0].encode('utf-8'))
    assert await stream.read_bytes(1) == b'\x01'
    return Connection(stream, (host, port), api_version, app)
