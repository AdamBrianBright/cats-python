import os
from abc import ABCMeta
from asyncio import sleep
from datetime import datetime
from inspect import isasyncgen, isgenerator
from io import BytesIO
from pathlib import Path
from struct import Struct
from typing import Any, Dict, Union

from cats.codecs import Codec
from cats.compression import Compressor
from cats.errors import MalformedDataError, ProtocolError
from cats.headers import Headers
from cats.typing import BytesAnyGen
from cats.utils import tmp_file

__all__ = [
    'MAX_SEND_CHUNK_SIZE',
    'BaseResponse',
    'Response',
    'StreamResponse',
    'InputResponse',
]

MAX_SEND_CHUNK_SIZE = 1 << 25


class BaseResponse:
    HEADER_SEPARATOR = b'\x00\x00'

    __slots__ = ('headers', 'data',)

    def __init__(self, data: Any = None, headers: Union[Dict[str, Any], Headers] = None):
        if headers is not None and not isinstance(headers, dict):
            raise MalformedDataError('Invalid Headers provided')
        self.data = data
        self.headers = Headers(headers or {})

    async def send_to_conn(self, conn):
        raise NotImplementedError

    def sleep(self, download_speed: int):
        start = datetime.now()
        yield 0
        while True:
            if download_speed:
                n = max(min(1.0 - (datetime.now() - start).total_seconds(), 1.0), 0)
                start = datetime.now()
                yield n
            else:
                yield 0


class BasicResponse(BaseResponse, metaclass=ABCMeta):
    __slots__ = ('message_id', 'data_type', '_data_len', 'compression', 'encoded', 'offset')

    def __init__(self, data: Any = None, headers: Union[Dict[str, Any], Headers] = None,
                 compression: int = None, data_type: int = None):
        self.compression = compression
        self.data_type = data_type
        self.message_id = 0
        self._data_len = 0
        self.offset: int = 0
        self.encoded: bool = False
        super().__init__(data, headers)

    async def _encode_data(self, conn):
        if self.encoded:
            if self.data_type is None:
                raise MalformedDataError('Response payload marked as encoded but type is not specified')
            elif not isinstance(self.data, (bytes, bytearray, memoryview, Path)):
                raise MalformedDataError('Response payload marked as encoded but data type is not binary')
            return

        self.data, self.data_type = await Codec.encode(self.data, self.headers, self.offset)

        if isinstance(self.data, Path):
            self.data, buff = tmp_file(), self.data
            self.compression = await Compressor.compress_file(buff, self.data, self.compression)
            self._data_len = os.path.getsize(self.data.resolve().as_posix())
        else:
            self.data, self.compression = await Compressor.compress(self.data, self.compression)
            self._data_len = len(self.data)

        self.encoded = True

    async def _write_to_stream(self, conn):
        fh = self.data.open('rb') if isinstance(self.data, Path) else BytesIO(self.data)
        try:
            left = self._data_len
            max_chunk_size = conn.download_speed or MAX_SEND_CHUNK_SIZE
            sleeper = self.sleep(conn.download_speed)

            while left > 0:
                await sleep(next(sleeper))
                size = min(left, max_chunk_size)
                chunk = fh.read(size)
                left -= size
                conn.reset_idle_timer()
                await conn.stream.write(chunk)
        finally:
            fh.close()


class Response(BasicResponse):
    __slots__ = ('status', 'handler_id',)
    struct = Struct('>HHQBBI')
    header_type = bytes([0])

    def __init__(self, data: Any = None, headers: Union[Dict[str, Any], Headers] = None,
                 status: int = 200, compression: int = None,
                 data_type: int = None):
        if status is None:
            status = 200
        elif not isinstance(status, int):
            raise MalformedDataError('Invalid status type')
        if compression is not None and not isinstance(compression, int):
            raise MalformedDataError('Invalid compression type')
        if data_type is not None and not isinstance(data_type, int):
            raise MalformedDataError('Invalid data type provided')

        super().__init__(data=data, headers=headers, compression=compression, data_type=data_type)

        self.status = status
        self.handler_id: int = 0

    async def send_to_conn(self, conn):
        await self._encode_data(conn)

        try:
            if self.status is not None and 'Status' not in self.headers:
                self.headers['Status'] = self.status
            message_headers = self.headers.encode() + self.HEADER_SEPARATOR

            header = self.header_type + self.struct.pack(
                self.handler_id,
                self.message_id,
                round(datetime.now().timestamp() * 1000),
                self.data_type,
                self.compression,
                self._data_len + len(message_headers)
            ) + message_headers

            conn.reset_idle_timer()
            async with conn.lock_write():
                await conn.stream.write(header)
                await self._write_to_stream(conn)
        finally:
            if isinstance(self.data, Path):
                self.data.unlink(missing_ok=True)


class StreamResponse(Response):
    struct = Struct('>HHQBB')
    header_type = bytes([1])

    def __init__(self, data: BytesAnyGen, data_type: int, headers: Union[Dict[str, Any], Headers] = None,
                 status: int = 200, compression: int = None):
        if not isgenerator(data) and not isasyncgen(data):
            raise MalformedDataError('StreamResponse supports only byte generators')
        super().__init__(data=data, headers=headers, status=status, compression=compression, data_type=data_type)

    async def send_to_conn(self, conn):
        await self._encode_data(conn)

        header = self.header_type + self.struct.pack(
            self.handler_id,
            self.message_id,
            round(datetime.now().timestamp() * 1000),
            self.data_type,
            self.compression
        )

        if self.status is not None and 'Status' not in self.headers:
            self.headers['Status'] = self.status
        message_headers = self.headers.encode()

        conn.reset_idle_timer()
        async with conn.lock_write():
            await conn.stream.write(header)
            await conn.stream.write(len(message_headers).to_bytes(4, 'big', signed=False))
            await conn.stream.write(message_headers)
            await self._write_to_stream(conn)

    async def _encode_data(self, conn):
        if self.encoded:
            if self.data_type is None:
                raise MalformedDataError('StreamResponse payload marked as encoded but type is not specified')
            elif not isasyncgen(self.data):
                raise MalformedDataError('StreamResponse payload marked as encoded but data type is not AsyncGenerator')
            return

        if self.compression is None:
            self.compression = await Compressor.propose_compression(b'0' * 5000)

        if isgenerator(self.data):
            self.data = self._sync_gen(self.data, conn.download_speed)
        elif isasyncgen(self.data):
            self.data = self._async_gen(self.data, conn.download_speed)
        else:
            raise MalformedDataError('StreamResponse payload is not (Async)Generator[Bytes, None, None]')

        self.encoded = True

    async def _write_to_stream(self, conn):
        sleeper = self.sleep(conn.download_speed)
        offset = self.offset

        async for chunk in self.data:
            if offset > 0:
                i = min(offset, len(chunk))
                chunk = chunk[i:]
                offset -= i
            if not chunk:
                continue
            await sleep(next(sleeper))
            if not isinstance(chunk, (bytes, bytearray, memoryview)):
                raise MalformedDataError('Provided data chunk is not binary')

            chunk, _ = await Compressor.compress(chunk, self.compression)
            chunk_size = len(chunk)
            if chunk_size >= 1 << 32:
                raise ProtocolError('Provided data chunk exceeded max chunk size')

            conn.reset_idle_timer()
            await conn.stream.write(chunk_size.to_bytes(4, 'big', signed=False))
            await conn.stream.write(chunk)
        await conn.stream.write(b'\x00\x00\x00\x00')

    async def _async_gen(self, gen, download_speed: int):
        max_chunk_size = download_speed or MAX_SEND_CHUNK_SIZE
        async for item in gen:
            left = len(item)
            while left > 0:
                s = min(left, max_chunk_size)
                yield item[:s]
                item = item[s:]
                left -= s

    async def _sync_gen(self, gen, download_speed: int):
        max_chunk_size = download_speed or MAX_SEND_CHUNK_SIZE
        for item in gen:
            left = len(item)
            while left > 0:
                s = min(left, max_chunk_size)
                yield item[:s]
                item = item[s:]
                left -= s


class InputResponse(BasicResponse):
    struct = Struct('>HBBI')
    header_type = bytes([2])

    async def send_to_conn(self, conn):
        await self._encode_data(conn)

        try:
            message_headers = self.headers.encode() + self.HEADER_SEPARATOR
            header = self.header_type + self.struct.pack(
                self.message_id,
                self.data_type,
                self.compression,
                self._data_len + len(message_headers)
            ) + message_headers

            conn.reset_idle_timer()
            async with conn.lock_write():
                await conn.stream.write(header)
                await self._write_to_stream(conn)
        finally:
            if isinstance(self.data, Path):
                self.data.unlink(missing_ok=True)
