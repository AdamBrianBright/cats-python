from abc import ABCMeta
from collections import defaultdict
from dataclasses import dataclass
from types import GeneratorType
from typing import Any, Awaitable, Callable, Coroutine, DefaultDict, Dict, List, Optional, Set, Tuple, Type, Union

import ujson

from cats.codecs import Codec, Json
from cats.headers import Headers
from cats.server.request import InputRequest, Request
from cats.server.response import Response

try:
    from django.db.models import QuerySet
    from rest_framework.serializers import BaseSerializer
except ImportError:
    class QuerySet:
        pass


    class BaseSerializer:
        pass

__all__ = [
    'HandlerFunc',
    'HandlerItem',
    'Api',
    'Handler',
]

HandlerFunc = Callable[[Request], Coroutine[Optional[Response]]]


@dataclass
class HandlerItem:
    id: int
    name: str
    callback: Callable
    version: Optional[int] = None
    end_version: Optional[int] = None


class Api:
    def __init__(self):
        self._handlers: DefaultDict[int, List[HandlerItem]] = defaultdict(list)

    def on(self, id: int, name: str = None, version: int = None, end_version: int = None):
        def wrapper(fn: HandlerFunc) -> HandlerFunc:
            self.register(HandlerItem(id, name, fn, version, end_version))
            return fn

        return wrapper

    def register(self, handler: HandlerItem):
        if handler in self._handlers[handler.id]:
            return

        assert handler.version is None or handler.end_version is None or handler.version <= handler.end_version, \
            f'Invalid version range for handler {handler.id}: [{handler.version}..{handler.end_version}]'

        if handler.version is not None or handler.end_version is not None:
            assert handler.version is not None, f'Initial version is not provided for {handler}'

            try:
                last_handler = self._handlers[handler.id][-1]
                assert last_handler.version is not None or last_handler.end_version is not None, \
                    f'Attempted to add versioned {handler} to wildcard'

                if last_handler.end_version is not None:
                    assert last_handler.end_version < handler.version, \
                        f'Handler {handler} overlap {last_handler} version'
                else:
                    assert last_handler.version < handler.version, \
                        f'Handler {handler} overlap {last_handler} version'
                    last_handler.end_version = handler.version - 1
            except IndexError:
                pass
        self._handlers[handler.id].append(handler)

    @property
    def handlers(self):
        return self._handlers

    def update(self, app: 'Api'):
        self._handlers.update(app.handlers)

    def compute(self) -> Dict[int, Union[List[HandlerItem], HandlerItem]]:
        result: Dict[int, Union[List[HandlerItem], HandlerItem]] = {}
        for handler_id, handler_list in self._handlers.items():
            if not handler_list:
                continue

            elif len(handler_list) == 1 and handler_list[0].version is None and handler_list[0].end_version is None:
                result[handler_id] = handler_list[0]
            else:
                result[handler_id] = handler_list

        return result


class Handler(metaclass=ABCMeta):
    handler_id: int

    Loader: Optional[Type[BaseSerializer]] = None
    Dumper: Optional[Type[BaseSerializer]] = None
    required_type: Optional[Union[int, Tuple[int], Set[int], List[int]]] = None

    def __init__(self, request: Request):
        self.request = request

    def __init_subclass__(cls, /, api: Api, id: int, name: str = None, version: int = None, end_version: int = None):
        if api is None:
            return

        assert id is not None

        assert cls.Loader is None or (isinstance(cls.Loader, type) and issubclass(cls.Loader, BaseSerializer)), \
            'Handler Loader must be subclass of rest_framework.serializers.BaseSerializer'
        assert cls.Dumper is None or (isinstance(cls.Dumper, type) and issubclass(cls.Dumper, BaseSerializer)), \
            'Handler Dumper must be subclass of rest_framework.serializers.BaseSerializer'

        item = HandlerItem(id, name, cls._to_func(), version, end_version)
        api.register(item)
        cls.handler_id = id

    async def prepare(self) -> None:
        if self.required_type is not None:
            await self._check_required_type()

    async def handle(self):
        raise NotImplementedError

    async def _check_required_type(self):
        types = self.required_type
        if isinstance(types, int):
            types = (types,)
        if self.request.data_type not in types:
            raise ValueError('Received payload type is not acceptable')

    @classmethod
    def _to_func(cls) -> HandlerFunc:
        async def wrapper(request: Request) -> Optional[Response]:
            handler = cls(request=request)
            await handler.prepare()
            return await handler.handle()

        return wrapper

    async def json_load(self, many: bool = False) -> Json:
        if self.request.data_type != Codec.T_JSON:
            raise TypeError('Unsupported data type. Expected JSON')

        data = self.request.data
        if self.Loader is not None:
            if many is None:
                many = isinstance(data, list)
            form = self.Loader(data=data, many=many)
            form.is_valid(raise_exception=True)
            return form.validated_data
        else:
            return data

    async def json_dump(self, data, headers: Union[Dict[str, Any], Headers] = None,
                        status: int = 200, many: bool = None) -> Response:
        if many is None:
            many = isinstance(data, (list, tuple, set, QuerySet, GeneratorType))

        if self.Dumper is not None:
            data = self.Dumper(data, many=many).data
        else:
            ujson.encode(data)

        return Response(data=data, headers=headers, status=status)

    def input(self, data: Any) -> Awaitable['InputRequest']:
        return self.request.input(data=data)
