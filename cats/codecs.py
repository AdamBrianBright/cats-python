from dataclasses import dataclass
from io import BytesIO
from os.path import getsize
from pathlib import Path
from typing import Any, Dict, IO, List, Optional, Type, Union

import ujson

from cats.headers import Headers
from cats.utils import tmp_file

__all__ = [
    'NULL',
    'FileInfo',
    'Files',
    'Byte',
    'Json',
    'BaseCodec',
    'ByteCodec',
    'JsonCodec',
    'FileCodec',
    'Codec',
]


class NULL:
    """JSON null placeholder"""


Byte = Union[bytes, bytearray, memoryview]
Json = Union[str, int, float, dict, list, bool, type(None), Type[NULL]]
File = Union[Path, str]


@dataclass
class FileInfo:
    name: str
    path: Path
    size: int
    mime: Optional[str]


Files = Dict[str, FileInfo]


class BaseCodec:
    type_id: int
    type_name: str

    @classmethod
    async def encode(cls, data: Any, headers) -> bytes:
        """
        :raise TypeError: Encoder doesn't support this type
        :raise ValueError: Failed to encode
        """
        raise NotImplementedError

    @classmethod
    async def decode(cls, data: Union[bytes, Path], headers) -> Any:
        """
        :raise TypeError: Encoder doesn't support this type
        :raise ValueError: Failed to decode
        """
        raise NotImplementedError


class ByteCodec(BaseCodec):
    type_id = 0x00
    type_name = 'bytes'

    @classmethod
    async def encode(cls, data: Byte, headers: Headers, offset: int) -> bytes:
        if data is not None and not isinstance(data, (bytes, bytearray, memoryview)):
            raise TypeError(f'{cls.__name__} does not support {type(data).__name__}')

        return (bytes(data) if data else bytes())[offset:]

    @classmethod
    async def decode(cls, data: bytes, headers) -> bytes:
        return bytes(data) if data else bytes()


class JsonCodec(BaseCodec):
    type_id = 0x01
    type_name = 'json'
    encoding = 'utf-8'

    @classmethod
    async def encode(cls, data: Json, headers: Headers, offset: int) -> bytes:
        if not isinstance(data, (str, int, float, dict, list, bool, type(None))):
            raise TypeError(f'{cls.__name__} does not support {type(data).__name__}')

        return ujson.encode(data, ensure_ascii=False).replace("</", "<\\/").encode(cls.encoding)[offset:]

    @classmethod
    async def decode(cls, data: bytes, headers) -> Json:
        if not data:
            return {}

        try:
            data = data.decode(cls.encoding)
            if not data:
                return {}
            return ujson.decode(data)
        except ValueError:
            raise ValueError('Failed to parse JSON from data')


FILE_TYPES = Union[
    Path, List[Path], Dict[str, Path],
    FileInfo, List[FileInfo], Dict[str, FileInfo],
]


class FileCodec(BaseCodec):
    type_id = 0x02
    type_name = 'files'
    encoding = 'utf-8'

    @classmethod
    def path_to_file_info(cls, path: Path) -> FileInfo:
        if not isinstance(path, Path):
            raise TypeError
        return FileInfo(path.name, path, getsize(path.as_posix()), None)

    @classmethod
    def normalize_input(cls, data: FILE_TYPES) -> Files:
        if isinstance(data, Path):
            data = cls.path_to_file_info(data)
        elif isinstance(data, list):
            res = []
            for i in data:
                if not isinstance(i, (FileInfo, Path)):
                    raise TypeError
                res.append(i if isinstance(i, FileInfo) else cls.path_to_file_info(i))

        elif isinstance(data, dict):
            res = {}
            for k, v in data.items():
                if not isinstance(k, str) or not isinstance(v, (FileInfo, Path)):
                    raise TypeError
                res[k] = v if isinstance(v, FileInfo) else cls.path_to_file_info(v)
        elif not isinstance(data, FileInfo):
            raise TypeError

        if isinstance(data, FileInfo):
            return {data.name: data}
        elif isinstance(data, list):
            return {i.name: i for i in data}
        else:
            return data

    @classmethod
    async def encode(cls, data: FILE_TYPES, headers: Headers, offset: int) -> Path:
        tmp = tmp_file()
        try:
            buff = tuple(cls.normalize_input(data).items())
            header = []
            with tmp.open('wb') as fh:
                for key, info in buff:
                    left = info.size - offset
                    offset = max(0, offset - left)
                    if left < 0:
                        continue
                    header.append({"key": key, "name": info.name, "size": left, "type": info.mime})
                    with info.path.open('rb') as f_fh:
                        f_fh.seek(info.size - left)
                        while left > 0:
                            buff = f_fh.read(1 << 24)
                            if not len(buff):
                                raise ValueError
                            fh.write(buff)
                            left -= len(buff)
            headers['Files'] = header
            return tmp

        except (KeyError, ValueError, TypeError, AttributeError):
            tmp.unlink(missing_ok=True)
            raise TypeError(f'{cls.__name__} does not support {type(data).__name__}')

    @classmethod
    async def decode(cls, data: Union[Path, bytes, bytearray], headers) -> Files:
        result = {}
        buff = data.open('rb') if isinstance(data, Path) else BytesIO(data)

        try:
            if 'Files' not in headers:
                raise ValueError('Failed to parse Files meta data from headers')

            header = headers['Files']

            if not isinstance(header, list):
                raise ValueError

            for node in header:
                if not isinstance(node, dict):
                    raise ValueError

                tmp = await cls._unpack_file(buff, node)
                result[node['key']] = FileInfo(
                    name=node['name'],
                    path=tmp,
                    size=node['size'],
                    mime=node.get('type'),
                )

            return result
        except (KeyError, ValueError, TypeError):
            for v in result.values():
                v.path.unlink(missing_ok=True)
            raise ValueError('Failed to parse Files form data')
        finally:
            buff.close()

    @classmethod
    async def _unpack_file(cls, fh: IO, node) -> Path:
        tmp = tmp_file()
        left = node['size']
        with tmp.open('wb') as node_fh:
            while left > 0:
                buff = fh.read(min(left, 1 << 24))
                if not len(buff):
                    raise ValueError
                node_fh.write(buff)
                left -= len(buff)
        return tmp


class Codec:
    T_BYTE = ByteCodec.type_id
    T_JSON = JsonCodec.type_id
    T_FILE = FileCodec.type_id

    codecs = {
        T_BYTE: ByteCodec,
        T_JSON: JsonCodec,
        T_FILE: FileCodec,
    }

    @classmethod
    async def encode(cls, buff: Union[Byte, Json, FILE_TYPES], headers: Headers, offset: int = 0) -> (bytes, int):
        """
        Takes any supported data type and returns tuple (encoded: bytes, type_id: int)
        """
        for type_id, codec in cls.codecs.items():
            try:
                encoded = await codec.encode(buff, headers, offset)
                return encoded, type_id
            except TypeError:
                continue

        raise TypeError(f'Failed to encode data: Type {type(buff).__name__} not supported')

    @classmethod
    async def decode(cls, buff: Union[Byte, Path], data_type: int, headers: Headers) -> Union[Byte, Json, Files]:
        """
        Takes byte buffer, type_id and try to decode it to internal data types
        """
        if data_type not in cls.codecs:
            raise TypeError(f'Failed to decode data: Type {data_type} not supported')

        return await cls.codecs[data_type].decode(buff, headers)

    def get_codec_name(self, type_id: int, default: str = 'unknown') -> str:
        """
        Returns Type Name by it's id (w/ fallback to default)
        :param type_id:
        :param default:
        :return:
        """
        try:
            return self.codecs[type_id].type_name
        except KeyError:
            return default
