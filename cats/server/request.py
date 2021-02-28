import os
from abc import ABCMeta
from asyncio import Future
from datetime import datetime, timezone
from struct import Struct
from typing import Any, Dict, Optional, Type

from cats.codecs import Codec
from cats.compression import Compressor
from cats.errors import ProtocolError
from cats.headers import Headers
from cats.server.response import InputResponse
from cats.utils import tmp_file

__all__ = [
    'BaseRequest',
    'Request',
    'StreamRequest',
    'InputRequest',
]


class BaseRequest(dict):
    __slots__ = ('conn', 'message_id', 'headers', 'data',)
    __registry__: Dict[int, Type['BaseRequest']] = {}
    type_id: int
    struct: Struct
    HEADER_SEPARATOR = b'\x00\x00'

    def __init__(self, conn, message_id: int):
        if self.__class__ == BaseRequest:
            raise RuntimeError('Creation of BaseRequest instances are prohibited')
        super().__init__()
        self.conn = conn
        self.message_id = message_id
        self.headers = Headers()
        self.data = None

    def __init_subclass__(cls, /, type_id: int = 0, struct: Struct = None, abstract: bool = False):
        if abstract:
            return
        assert isinstance(type_id, int) and type_id >= 0, f'Invalid {type_id = } provided'
        assert isinstance(struct, Struct), f'Invalid {struct = } provided'
        assert type_id not in cls.__registry__, f'Request with {type_id = } already assigned'
        cls.__registry__[type_id] = cls
        setattr(cls, 'type_id', type_id)
        setattr(cls, 'struct', struct)

    @classmethod
    def get_class_by_type_id(cls, message_type: int) -> Optional[Type['BaseRequest']]:
        return cls.__registry__.get(message_type)

    async def input(self, data: Any = None, headers: Headers = None,
                    data_type: int = None, compression: int = None) -> 'InputRequest':
        fut = Future()
        if self.message_id in self.conn.input_queue:
            raise ProtocolError(f'Input query with MID {self.message_id} already exists')

        self.conn.input_queue[self.message_id] = fut
        response = InputResponse(data, headers, compression=compression, data_type=data_type)
        response.message_id = self.message_id
        await response.send_to_conn(self.conn)
        return await fut

    @classmethod
    async def recv_from_conn(cls, conn) -> 'BaseRequest':
        raise NotImplementedError


class BasicRequest(BaseRequest, metaclass=ABCMeta, abstract=True):
    __slots__ = ('data_type', 'data_len', 'compression')

    def __init__(self, conn, message_id: int, data_type: int, compression: int = 0, data_len: int = 0):
        self.data_len = data_len
        self.data_type = data_type
        self.compression = compression
        super().__init__(conn, message_id)

    async def recv_data(self):
        left = self.data_len
        if left > self.conn.MAX_PLAIN_DATA_SIZE:
            if self.data_type != Codec.T_FILE:
                raise ProtocolError(f'Attempted to send message larger than {self.conn.MAX_PLAIN_DATA_SIZE}b')

            src, dst = tmp_file(), tmp_file()

            try:
                with src.open('wb') as fh:
                    while left > 0:
                        self.conn.reset_idle_timer()
                        chunk = await self.conn.stream.read_bytes(min(left, 1 << 20), partial=True)
                        left -= len(chunk)
                        fh.write(chunk)

                await Compressor.decompress_file(src, dst, compression=self.compression)
                self.data = await Codec.decode(dst, self.data_type, self.headers)
            except Exception:
                dst.unlink(missing_ok=True)
                raise
            finally:
                src.unlink(missing_ok=True)
        else:
            buff = bytearray()
            while left > 0:
                self.conn.reset_idle_timer()
                chunk = await self.conn.stream.read_bytes(min(left, 1 << 20), partial=True)
                left -= len(chunk)
                buff.extend(chunk)

            buff = await Compressor.decompress(buff, compression=self.compression)
            self.data = await Codec.decode(buff, self.data_type, self.headers)


class Request(BasicRequest, type_id=0x00, struct=Struct('>HHHQBBI')):
    __slots__ = ('handler_id', 'status', 'send_time', 'data_type', 'data_len', 'compression')

    def __init__(self, conn, message_id: int, handler_id: int, data_type: int,
                 status: int = None, send_time: datetime = None, compression: int = 0, data_len: int = 0):
        self.handler_id = handler_id
        self.status = status or 200
        self.send_time = send_time or datetime.now(timezone.utc)
        super().__init__(conn=conn, message_id=message_id,
                         compression=compression, data_type=data_type, data_len=data_len)

    @classmethod
    async def recv_from_conn(cls, conn) -> 'Request':
        conn.reset_idle_timer()
        buff = await conn.stream.read_bytes(cls.struct.size)
        handler_id, message_id, status, send_time, data_type, compression, data_len = cls.struct.unpack(buff)

        headers = await conn.stream.read_until(cls.HEADER_SEPARATOR, data_len)
        data_len -= len(headers)
        headers = Headers.decode(headers[:-2])

        request = cls(
            conn=conn,
            message_id=message_id,
            handler_id=handler_id,
            status=status,
            send_time=datetime.fromtimestamp(send_time / 1000, tz=timezone.utc),
            data_type=data_type,
            compression=compression,
            data_len=data_len
        )
        request.headers = headers
        await request.recv_data()
        return request


class StreamRequest(Request, type_id=0x01, struct=Struct('>HHHQBB')):
    def __init__(self, conn, message_id: int, handler_id: int, data_type: int,
                 status: int = None, send_time: datetime = None):
        super().__init__(conn, message_id, handler_id, data_type, status, send_time)

    @classmethod
    async def recv_from_conn(cls, conn) -> 'StreamRequest':
        conn.reset_idle_timer()
        buff = await conn.stream.read_bytes(cls.struct.size)
        handler_id, message_id, status, send_time, data_type, compression = cls.struct.unpack(buff)

        request = cls(
            conn=conn,
            message_id=message_id,
            handler_id=handler_id,
            data_type=data_type,
            status=status,
            send_time=send_time,
        )
        request.compression = compression

        headers_size = int.from_bytes(await conn.stream.read_bytes(4), 'big', signed=False)
        request.headers = Headers.decode(await conn.stream.read_bytes(headers_size))
        await request.recv_data()
        return request

    async def recv_data(self):
        data_len = 0
        buff = tmp_file()
        try:
            with buff.open('wb') as fh:
                self.conn.reset_idle_timer()
                while chunk_size := int.from_bytes(await self.conn.stream.read_bytes(4), 'big', signed=False):
                    if chunk_size > 1 << 24:
                        data_len += await self._recv_large_chunk(fh, chunk_size)
                    else:
                        data_len += await self._recv_small_chunk(fh, chunk_size)

            if data_len > self.conn.MAX_PLAIN_DATA_SIZE:
                if self.data_type != Codec.T_FILE:
                    raise ProtocolError(f'Attempted to send message larger than {self.conn.MAX_PLAIN_DATA_SIZE}b')
                decode = buff
            elif self.data_type != Codec.T_FILE:
                with buff.open('rb') as _fh:
                    decode = _fh.read()
            self.data = await Codec.decode(decode, self.data_type, self.headers)
            self.data_len = data_len
        finally:
            buff.unlink(missing_ok=True)

    async def _recv_large_chunk(self, fh, chunk_size):
        left = chunk_size
        part, dst = tmp_file(), tmp_file()
        try:
            with part.open('wb') as tmp:
                while left > 0:
                    chunk = await self.conn.stream.read_bytes(left, partial=True)
                    left -= len(chunk)
                    tmp.write(chunk)
            await Compressor.decompress_file(part, dst, compression=self.compression)
            data_len = os.path.getsize(dst.resolve().as_posix())
            with dst.open('rb') as tmp:
                while i := tmp.read(1 << 24):
                    fh.write(i)
            return data_len
        finally:
            part.unlink(missing_ok=True)
            dst.unlink(missing_ok=True)

    async def _recv_small_chunk(self, fh, chunk_size):
        left = chunk_size
        part = bytearray()
        while left > 0:
            chunk = await self.conn.stream.read_bytes(left, partial=True)
            left -= len(chunk)
            part += chunk
        part = await Compressor.decompress(part, compression=self.compression)
        fh.write(part)
        return len(part)


class InputRequest(BasicRequest, type_id=0x02, struct=Struct('>HBBI')):
    @classmethod
    async def recv_from_conn(cls, conn) -> 'InputRequest':
        buff = await conn.stream.read_bytes(cls.struct.size)
        message_id, data_type, compression, data_len = cls.struct.unpack(buff)

        headers = await conn.stream.read_until(cls.HEADER_SEPARATOR, data_len)
        data_len -= len(headers)
        headers = Headers.decode(headers[:-2])

        request = cls(conn=conn, message_id=message_id, data_type=data_type, compression=compression, data_len=data_len)
        request.headers = headers
        await request.recv_data()
        return request

    async def answer(self, data: Any = None, headers: Headers = None,
                     compression: int = None, data_type: int = None) -> None:
        response = InputResponse(data=data, headers=headers, compression=compression, data_type=data_type)
        response.message_id = self.message_id
        response.offset = self.headers.get('Offset', 0)
        await response.send_to_conn(self.conn)


class _DownloadSpeed(BaseRequest, type_id=0x05, struct=Struct('>I')):
    @classmethod
    async def recv_from_conn(cls, conn) -> '_DownloadSpeed':
        conn.reset_idle_timer()
        buff = await conn.stream.read_bytes(cls.struct.size)
        speed, *_ = cls.struct.unpack(buff)
        request = cls(conn=conn, message_id=0)
        request.data = speed
        return request
