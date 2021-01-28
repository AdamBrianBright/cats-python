import hashlib
from asyncio import wait_for
from datetime import datetime, timezone
from typing import List

from cats.conn import Connection
from cats.events import Event

__all__ = [
    'Handshake',
    'SHA256TimeHandshake',
]


class Handshake:
    async def validate(self, conn: Connection) -> None:
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

    async def validate(self, conn: Connection) -> None:
        handshake: bytes = await wait_for(conn.stream.read_bytes(64), self.timeout)
        if handshake.decode('utf-8') not in self.get_hashes():
            await conn.app.trigger(Event.ON_HANDSHAKE_FAIL, conn=conn, handshake=handshake)
            raise ValueError('Invalid handshake')
        await conn.app.trigger(Event.ON_HANDSHAKE_PASS, conn=conn)
