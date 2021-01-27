import gzip
import os
import shutil
from pathlib import Path
from typing import Union

__all__ = [
    'Compressor',
]


class BaseCompressor:
    type_id: int

    @classmethod
    async def compress(cls, data: bytes) -> bytes:
        raise NotImplementedError

    @classmethod
    async def decompress(cls, data: bytes) -> bytes:
        raise NotImplementedError

    @classmethod
    async def compress_file(cls, src: Path, dst: Path) -> None:
        raise NotImplementedError

    @classmethod
    async def decompress_file(cls, src: Path, dst: Path) -> None:
        raise NotImplementedError


class DummyCompressor(BaseCompressor):
    type_id = 0x00

    @classmethod
    async def compress(cls, data: bytes) -> bytes:
        return data

    @classmethod
    async def decompress(cls, data: bytes) -> bytes:
        return data

    @classmethod
    async def compress_file(cls, src: Path, dst: Path) -> None:
        shutil.copy(src.resolve().as_posix(), dst.resolve().as_posix())

    @classmethod
    async def decompress_file(cls, src: Path, dst: Path) -> None:
        shutil.copy(src.resolve().as_posix(), dst.resolve().as_posix())


class GzipCompressor(BaseCompressor):
    type_id = 0x01

    @classmethod
    async def compress(cls, data: bytes) -> bytes:
        return gzip.compress(data, compresslevel=9)

    @classmethod
    async def decompress(cls, data: bytes) -> bytes:
        return gzip.decompress(data)

    @classmethod
    async def compress_file(cls, src: Path, dst: Path) -> None:
        with src.open('rb') as rc:
            with gzip.open(dst.resolve().as_posix(), 'wb', compresslevel=9) as wc:
                while line := rc.read(1 << 24):
                    wc.write(line)

    @classmethod
    async def decompress_file(cls, src: Path, dst: Path) -> None:
        with gzip.open(src.resolve().as_posix(), 'rb') as rc:
            with dst.open('wb') as wc:
                while line := rc.read(1 << 24):
                    wc.write(line)


class Compressor:
    T_NONE = 0b0000
    T_GZIP = 0b0001
    compressors = {
        T_NONE: DummyCompressor,
        T_GZIP: GzipCompressor,
    }

    @classmethod
    async def compress(cls, buff: bytes, compression: int = None) -> (bytes, int):
        try:
            if compression is None:
                compression = await cls.propose_compression(buff)

            buff = await cls.compressors[compression].compress(buff)
            return buff, compression

        except (KeyError, ValueError, TypeError) as err:
            raise ValueError(f'Failed to compress data: {str(err)}')

    @classmethod
    async def decompress(cls, buff: bytes, compression: int) -> bytes:
        try:
            return await cls.compressors[compression].decompress(buff)
        except (KeyError, ValueError, TypeError) as err:
            raise ValueError(f'Failed to decompress data: {str(err)}')

    @classmethod
    async def compress_file(cls, src: Path, dst: Path, compression: int = None) -> int:
        try:
            if compression is None:
                compression = await cls.propose_compression(src)

            await cls.compressors[compression].compress_file(src, dst)
            return compression
        except (KeyError, ValueError, TypeError) as err:
            raise ValueError(f'Failed to compress file: {str(err)}')

    @classmethod
    async def decompress_file(cls, src: Path, dst: Path, compression: int) -> None:
        try:
            await cls.compressors[compression].decompress_file(src, dst)
        except (KeyError, ValueError, TypeError) as err:
            raise ValueError(f'Failed to decompress file: {str(err)}')

    @classmethod
    async def propose_compression(cls, buff: Union[bytes, Path]):
        if isinstance(buff, bytes):
            if len(buff) > 4096:
                return cls.T_GZIP
            else:
                return cls.T_NONE

        elif isinstance(buff, Path):
            s = os.path.getsize(buff.as_posix())
            if s > 4096:
                return cls.T_GZIP
            else:
                return cls.T_NONE

        else:
            raise TypeError('Unsupported buffer type')
