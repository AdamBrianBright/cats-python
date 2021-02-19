import logging
import tempfile
from importlib import import_module

from pathlib import Path

from typing import Union

__all__ = [
    'require',
    'tmp_file',
    'bytes2hex',
    'enable_stream_debug',
]


def tmp_file(**kwargs) -> Path:
    kwargs['delete'] = kwargs.get('delete', False)
    return Path(tempfile.NamedTemporaryFile(**kwargs).name)


def require(dotted_path: str, /, *, strict: bool = True):
    """
    Import a dotted module path and return the attribute/class designated by the
    last name in the path. Raise ImportError if the import failed.
    """
    try:
        try:
            module_path, class_name = dotted_path.rsplit('.', 1)
        except ValueError as err:
            raise ImportError(f"{dotted_path} doesn't look like a module path") from err

        module = import_module(module_path)

        try:
            return getattr(module, class_name)
        except AttributeError as err:
            raise ImportError(f'Module "{module_path}" does not define a "{class_name}" attribute/class') from err
    except ImportError as err:
        logging.error(f'Failed to import {dotted_path}')
        if strict:
            raise err
        return None


def bytes2hex(buffer: Union[bytes, bytearray, memoryview], *, separator: str = ' ', prefix: bool = False) -> str:
    """
    Converts byte-like to HEX string

    :param buffer: what to encode
    :param separator: separator string
    :param prefix: use 0x prefix
    :return: HEX style string
    :raise TypeError:
    """
    if not isinstance(buffer, (bytes, bytearray, memoryview)):
        raise TypeError(f'Invalid buffer type = {type(buffer)}')

    hexadecimal = buffer.hex().upper()
    parts = (hexadecimal[i: i + 2] for i in range(0, len(hexadecimal), 2))
    if prefix:
        parts = ('0x' + part for part in parts)
    return separator.join(parts)


def enable_stream_debug():
    from tornado.iostream import IOStream
    rb = IOStream.read_bytes
    ru = IOStream.read_until
    wr = IOStream.write

    async def read_bytes(self: IOStream, num_bytes, partial: bool = False):
        chunk = await rb(self, num_bytes, partial=partial)
        print(f'[RECV {self.socket.getpeername()}] {bytes2hex(chunk)}')
        return chunk

    async def read_until(self: IOStream, delimiter: bytes, max_bytes: int = None):
        chunk = await ru(self, delimiter, max_bytes=max_bytes)
        print(f'[RECV {self.socket.getpeername()}] {bytes2hex(chunk)}')
        return chunk

    async def write(self: IOStream, data):
        print(f'[SEND {self.socket.getpeername()}] {bytes2hex(data)}')
        return await wr(self, data)

    IOStream.read_until = read_until
    IOStream.read_bytes = read_bytes
    IOStream.write = write
