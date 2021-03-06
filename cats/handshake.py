import hashlib
from asyncio import wait_for
from datetime import datetime, timezone
from typing import List

from cats.events import Event

__all__ = [
    'HandshakeError',
    'Handshake',
    'SHA256TimeHandshake',
]


class HandshakeError(ValueError):
    pass


class Handshake:
    async def validate(self, server, conn) -> None:
        raise NotImplementedError


class SHA256TimeHandshake(Handshake):
    def __init__(self, secret_key: bytes, valid_window: int = None, timeout: float = 5.0):
        assert isinstance(secret_key, bytes) and secret_key
        self.secret_key = secret_key
        self.valid_window = valid_window or 1
        self.timeout = timeout
        assert self.valid_window >= 1

    def get_hashes(self) -> List[str]:
        time = round(datetime.now(tz=timezone.utc).timestamp() / 10) * 10

        return [
            hashlib.sha256(self.secret_key + str(time + i * 10).encode('utf-8')).hexdigest()
            for i in range(-self.valid_window, self.valid_window + 1)
        ]

    async def validate(self, server, conn) -> None:
        handshake: bytes = await wait_for(conn.stream.read_bytes(64), self.timeout)
        if handshake.decode('utf-8') not in self.get_hashes():
            await conn.app.trigger(Event.ON_HANDSHAKE_FAIL, server=server, conn=conn, handshake=handshake)
            await conn.stream.write(b'\x00')
            raise HandshakeError('Invalid handshake')
        await conn.app.trigger(Event.ON_HANDSHAKE_PASS, server=server, conn=conn)
        await conn.stream.write(b'\x01')
