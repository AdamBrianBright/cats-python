import ujson

from cats.errors import ProtocolError
from cats.typing import Bytes

__all__ = [
    'Headers',
]


class Headers(dict):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for key, value in self.items():
            if not isinstance(key, str):
                raise ValueError

            if key == 'Offset' and (not isinstance(value, int) or value < 0):
                raise ProtocolError('Invalid offset header')

    def encode(self) -> bytes:
        return ujson.encode(self, ensure_ascii=False).encode('utf-8')

    @classmethod
    def decode(cls, headers: Bytes) -> 'Headers':
        return cls(ujson.decode(headers.decode('utf-8')))
