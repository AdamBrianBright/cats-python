from tornado.iostream import IOStream

from cats import Connection, SHA256TimeHandshake, Server

__all__ = [
    'init_cats_conn',
]


async def init_cats_conn(stream: IOStream, host: str, port: int, server: Server, api_version: int = 1) -> Connection:
    await stream.write(api_version.to_bytes(4, 'big', signed=False))
    await stream.read_bytes(8)
    server.handshake: SHA256TimeHandshake
    await stream.write(server.handshake.get_hashes()[0].encode('utf-8'))
    return Connection(stream, (host, port), api_version, server)
