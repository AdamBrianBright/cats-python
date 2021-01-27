import logging
import tempfile
from importlib import import_module

from pathlib import Path

__all__ = [
    'require',
    'tmp_file',
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
