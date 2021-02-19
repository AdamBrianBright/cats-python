import os
from asyncio import Future, sleep
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from inspect import isasyncgen, isgenerator
from io import BytesIO
from pathlib import Path
from struct import Struct
from typing import Any, Dict, IO, Optional, Tuple, Type, Union

import ujson

from cats.codecs import Codec, Files
from cats.compression import Compressor
from cats.headers import Headers
from cats.utils import tmp_file

__all__ = [
    'BaseRequest',
    'Request',
    'StreamRequest',
    'InputRequest',
    '_DownloadSpeed',
]

MAX_SEND_CHUNK_SIZE = 1 << 25


class BaseRequest(dict):
    __slots__ = ('conn', 'message_id', 'headers', 'data')
    __registry__: Dict[int, Type['BaseRequest']] = {}
    type_id: int
    struct: Struct
    is_writing: bool = False
    HEADER_SEPARATOR = b'\x00\x00'

    def __init__(self, conn, message_id: int, headers: Headers, data: Any):
        if self.__class__ == BaseRequest:
            raise NotImplementedError('Creation of BaseRequest instances are prohibited')
        super().__init__()
        self.conn = conn
        self.message_id = message_id
        self.headers = headers or {}
        self.data = data

    def __init_subclass__(cls, /, type_id: int, struct: Struct):
        if type_id in cls.__registry__:
            raise ValueError(f'Request with {type_id = } already assigned')
        cls.__registry__[type_id] = cls
        setattr(cls, 'type_id', type_id)
        setattr(cls, 'struct', struct)

    @classmethod
    def get_class_by_type_id(cls, message_type: int) -> Optional[Type['BaseRequest']]:
        return cls.__registry__.get(message_type)

    async def input(self, data: Any) -> 'InputRequest':
        fut = Future()
        if self.message_id in self.conn.input_queue:
            raise self.conn.ProtocolError(f'Input query with MID {self.message_id} already exists')

        self.conn.input_queue[self.message_id] = fut
        request = InputRequest(self.conn, self.message_id, self.headers, data)
        await request.send_to_conn()
        return await fut

    def __str__(self) -> str:
        return f'{self.__class__.__name__} {self.message_id} {self.conn} {self.data}'

    @classmethod
    async def recv_from_conn(cls, conn) -> 'BaseRequest':
        raise NotImplementedError

    async def send_to_conn(self, offset: int = 0) -> None:
        raise NotImplementedError

    @asynccontextmanager
    async def lock(self):
        while self.conn.is_sending:
            await sleep(0.05)
        self.conn.is_sending = True
        yield
        self.conn.is_sending = False

    @classmethod
    async def recv_headers(cls, conn, max_bytes: int) -> (Headers, int):
        _headers = await conn.stream.read_until(cls.HEADER_SEPARATOR, max_bytes)
        _size = len(_headers)
        headers = ujson.decode(_headers[:-2].decode('utf-8'))
        if not isinstance(headers, dict):
            raise conn.ProtocolError('Malformed Data Headers')

        for key, val in headers.items():
            if not isinstance(key, str):
                raise conn.ProtocolError('Malformed Data Headers')

            if key == 'Offset' and (not isinstance(val, int) or val < 0):
                raise conn.ProtocolError('Invalid offset header')

        return headers, _size

    async def _prepare_fh(self, data) -> Tuple[Any, IO, int, int]:
        if isinstance(data, Path):
            buff, data = data, tmp_file()
            compression = await Compressor.compress_file(buff, data)
            data_len = os.path.getsize(data.resolve().as_posix())
            fh = data.open('rb')
        elif isinstance(data, (bytes, bytearray, memoryview)):
            data, compression = await Compressor.compress(data)
            data_len = len(data)
            fh = BytesIO(data)
            fh.seek(0)
        else:
            raise self.conn.ProtocolError('Invalid data provided to request')
        return data, fh, data_len, compression

    async def _write_to_fh(self, data_len: int, fh: IO):
        left = data_len

        sleeper = self.sleep()
        while left > 0:
            await sleep(next(sleeper))
            s = min(left, self.conn.download_speed or MAX_SEND_CHUNK_SIZE)
            chunk = fh.read(s)
            left -= s
            self.conn.reset_idle_timer()
            await self.conn.stream.write(chunk)

    def sleep(self):
        start = datetime.now()
        yield 0
        while True:
            if self.conn.download_speed:
                n = max(min(1.0 - (datetime.now() - start).total_seconds(), 1.0), 0)
                start = datetime.now()
                yield n
            else:
                yield 0


class Request(BaseRequest, type_id=0x00, struct=Struct('>HHHQBBI')):
    __slots__ = ('handler_id', 'status', 'send_time', 'data_type')

    def __init__(self, conn, message_id: int, headers: Headers, data: Any, handler_id: int, data_type: int = None,
                 status: int = None, send_time: datetime = None):
        self.handler_id = handler_id
        self.status = status or 200
        self.send_time = send_time or datetime.now(timezone.utc)
        self.data_type = data_type
        super().__init__(conn, message_id, headers, data)

    @classmethod
    async def recv_from_conn(cls, conn) -> 'Request':
        conn.reset_idle_timer()
        buff = await conn.stream.read_bytes(cls.struct.size)
        handler_id, message_id, status, send_time, data_type, compression, data_len = cls.struct.unpack(buff)

        headers, headers_size = await cls.recv_headers(conn, data_len)
        data_len -= headers_size
        data = await cls.recv_data(conn, data_type, headers, data_len, compression)

        return cls(
            conn=conn,
            message_id=message_id,
            headers=headers,
            data=data,
            handler_id=handler_id,
            status=status,
            send_time=datetime.fromtimestamp(send_time / 1000, tz=timezone.utc),
            data_type=data_type,
        )

    @classmethod
    async def recv_data(cls, conn, data_type: int, headers, data_len: int, compression: int) -> Union[Files, Any]:
        left = data_len
        if data_len > conn.MAX_PLAIN_DATA_SIZE:
            if data_type != Codec.T_FILE:
                raise conn.ProtocolError(f'Attempted to send message larger than {conn.MAX_PLAIN_DATA_SIZE}b')

            src, dst = tmp_file(), tmp_file()

            try:
                with src.open('wb') as fh:
                    while left > 0:
                        conn.reset_idle_timer()
                        chunk = await conn.stream.read_bytes(min(left, 1 << 20), partial=True)
                        left -= len(chunk)
                        fh.write(chunk)

                await Compressor.decompress_file(src, dst, compression)
                return await Codec.decode(dst, data_type, headers)
            except Exception:
                dst.unlink(missing_ok=True)
                raise
            finally:
                src.unlink(missing_ok=True)
        else:
            buff = bytearray()
            while left > 0:
                conn.reset_idle_timer()
                chunk = await conn.stream.read_bytes(min(left, 1 << 20), partial=True)
                left -= len(chunk)
                buff.extend(chunk)

            buff = await Compressor.decompress(buff, compression)
            return await Codec.decode(buff, data_type, headers)

    async def send_to_conn(self, offset: int = 0) -> None:
        async with self.lock():
            data, data_type = await Codec.encode(self.data, self.headers, offset)
            fh = BytesIO()

            try:
                data, fh, data_len, compression = await self._prepare_fh(data)

                headers = self.headers or {}
                headers = ujson.encode(headers).encode('utf-8') + self.HEADER_SEPARATOR
                header = self.type_id.to_bytes(1, 'big', signed=False)
                header += self.struct.pack(
                    self.handler_id,
                    self.message_id,
                    self.status,
                    round(self.send_time.timestamp() * 1000),
                    data_type,
                    compression,
                    data_len + len(headers)
                )
                header += headers
                self.conn.reset_idle_timer()
                await self.conn.stream.write(header)

                await self._write_to_fh(data_len, fh)
            finally:
                fh.close()
                if isinstance(data, Path):
                    data.unlink(missing_ok=True)


class StreamRequest(Request, type_id=0x01, struct=Struct('>HHHQBB')):
    __slots__ = ('data_type', 'handler_id', 'status', 'send_time')

    def __init__(self, conn, message_id: int, headers: Headers, data: Any, handler_id: int, data_type: int,
                 status: int = None, send_time: datetime = None):
        super().__init__(conn, message_id, headers, data, handler_id, data_type, status, send_time)

    @classmethod
    async def recv_from_conn(cls, conn) -> 'StreamRequest':
        conn.reset_idle_timer()
        buff = await conn.stream.read_bytes(cls.struct.size)
        handler_id, message_id, status, send_time, data_type, compression = cls.struct.unpack(buff)

        headers_size = int.from_bytes(await conn.stream.read_bytes(4), 'big', signed=False)
        headers = await conn.stream.read_bytes(headers_size)
        headers = ujson.decode(headers.decode('utf-8'))
        data, data_type = await cls.recv_data(conn, data_type, compression)

        return cls(
            conn=conn,
            message_id=message_id,
            headers=headers,
            data=data,
            handler_id=handler_id,
            data_type=data_type,
            status=status,
            send_time=datetime.fromtimestamp(send_time / 1000, tz=timezone.utc),
        )

    @classmethod
    async def recv_data(cls, conn, data_type: int, compression: int, **kwargs) -> Tuple[Union[Files, Any], int]:
        data_len = 0
        buff, dst = tmp_file(), tmp_file()

        try:
            with buff.open('wb') as fh:
                conn.reset_idle_timer()
                while chunk_size := int.from_bytes(await conn.stream.read_bytes(4), 'big', signed=False):
                    conn.reset_idle_timer()
                    chunk = await conn.stream.read_bytes(chunk_size)
                    chunk = await Compressor.decompress(chunk, compression)
                    fh.write(chunk)
                    data_len += len(chunk)

            if data_len > conn.MAX_PLAIN_DATA_SIZE:
                if data_type != Codec.T_FILE:
                    raise conn.ProtocolError(f'Attempted to send message larger than {conn.MAX_PLAIN_DATA_SIZE}b')

                return await Codec.decode(dst, data_type, cls.headers), data_type

            else:
                with buff.open('rb') as fh:
                    data = fh.read()

                return await Codec.decode(data, data_type, cls.headers), data_type
        except Exception:
            dst.unlink(missing_ok=True)
            raise
        finally:
            buff.unlink(missing_ok=True)

    async def _async_gen(self, gen):
        async for item in gen:
            left = len(item)
            while left > 0:
                s = min(left, self.conn.download_speed or MAX_SEND_CHUNK_SIZE)
                yield item[:s]
                item = item[s:]
                left -= s

    async def _sync_gen(self, gen):
        for item in gen:
            left = len(item)
            while left > 0:
                s = min(left, self.conn.download_speed or MAX_SEND_CHUNK_SIZE)
                yield item[:s]
                item = item[s:]
                left -= s

    async def send_to_conn(self, offset: int = 0) -> None:
        async with self.lock():
            data = self.data
            compression = await Compressor.propose_compression(b'0' * 5000)
            if isgenerator(data):
                data = self._sync_gen(data)
            elif isasyncgen(data):
                data = self._async_gen(data)
            else:
                raise self.conn.ProtocolError('Provided invalid data to stream')

            headers = ujson.encode(self.headers).encode('utf-8')

            header = self.type_id.to_bytes(1, 'big', signed=False)
            header += self.struct.pack(
                self.handler_id,
                self.message_id,
                self.status,
                round(self.send_time.timestamp() * 1000),
                self.data_type,
                compression
            )

            await self.conn.stream.write(header)
            await self.conn.stream.write(len(headers).to_bytes(4, 'big', signed=False))
            await self.conn.stream.write(headers)

            sleeper = self.sleep()
            async for chunk in data:
                if offset > 0:
                    i = min(offset, len(chunk))
                    chunk = chunk[i:]
                    offset -= i
                if not chunk:
                    continue
                await sleep(next(sleeper))
                if not isinstance(chunk, (bytes, bytearray, memoryview)):
                    raise self.conn.ProtocolError('Provided data chunk is invalid')

                chunk, compression = await Compressor.compress(chunk, compression)

                chunk_size = len(chunk)
                if chunk_size >= 1 << 32:
                    raise self.conn.ProtocolError('Provided data chunk exceeded max size')

                self.conn.reset_idle_timer()
                await self.conn.stream.write(chunk_size.to_bytes(4, 'big', signed=False))
                await self.conn.stream.write(chunk)
            self.conn.reset_idle_timer()
            await self.conn.stream.write(b'\x00\x00\x00\x00')


class InputRequest(BaseRequest, type_id=0x02, struct=Struct('>HBBI')):

    @classmethod
    async def recv_from_conn(cls, conn) -> 'InputRequest':
        conn.reset_idle_timer()
        buff = await conn.stream.read_bytes(cls.struct.size)
        message_id, data_type, compression, data_len = cls.struct.unpack(buff)

        headers, headers_size = await cls.recv_headers(conn, data_len)
        data_len -= headers_size
        data = await Request.recv_data(conn, data_type, headers, data_len, compression)
        return cls(conn=conn, message_id=message_id, headers=headers, data=data)

    async def send_to_conn(self, offset: int = 0) -> None:
        async with self.lock():
            data, data_type = await Codec.encode(self.data, self.headers, offset)
            fh = BytesIO()

            try:
                data, fh, data_len, compression = await self._prepare_fh(data)

                headers = self.headers or {}
                headers = ujson.encode(headers).encode('utf-8') + self.HEADER_SEPARATOR
                header = self.type_id.to_bytes(1, 'big', signed=False)
                header += self.struct.pack(self.message_id, data_type, compression, data_len + len(headers))
                header += headers
                self.conn.reset_idle_timer()
                await self.conn.stream.write(header)

                await self._write_to_fh(data_len, fh)
            finally:
                fh.close()
                if isinstance(data, Path):
                    data.unlink(missing_ok=True)

    async def answer(self, data) -> None:
        response = InputRequest(self.conn, self.message_id, self.headers, data)
        await response.send_to_conn()


class _DownloadSpeed(BaseRequest, type_id=0x05, struct=Struct('>I')):
    @classmethod
    async def recv_from_conn(cls, conn) -> '_DownloadSpeed':
        conn.reset_idle_timer()
        buff = await conn.stream.read_bytes(cls.struct.size)
        speed, *_ = cls.struct.unpack(buff)
        return cls(conn=conn, message_id=0, headers={}, data=speed)

    async def send_to_conn(self, offset: int = 0) -> None:
        raise RuntimeError('Someone just had a stroke')
