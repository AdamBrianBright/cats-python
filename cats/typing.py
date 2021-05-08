from dataclasses import dataclass
from datetime import datetime
from typing import AsyncGenerator, Generator, Union

__all__ = [
    'Bytes',
    'BytesGen',
    'BytesAsyncGen',
    'BytesAnyGen',
    'PingData',
]

Bytes = Union[bytes, bytearray, memoryview]
BytesGen = Generator[Bytes, None, None]
BytesAsyncGen = AsyncGenerator[Bytes, None]
BytesAnyGen = Union[BytesGen, BytesAsyncGen]


@dataclass
class PingData:
    send_time: datetime
    recv_time: datetime
