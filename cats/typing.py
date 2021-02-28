from typing import AsyncGenerator, Generator, Union

__all__ = [
    'Bytes',
    'BytesGen',
    'BytesAsyncGen',
    'BytesAnyGen',
]
Bytes = Union[bytes, bytearray, memoryview]
BytesGen = Generator[Bytes, None, None]
BytesAsyncGen = AsyncGenerator[Bytes, None]
BytesAnyGen = Union[BytesGen, BytesAsyncGen]
