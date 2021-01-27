from collections import defaultdict
from inspect import isawaitable
from typing import Callable, DefaultDict, Iterable, List, Optional, Union

from cats.conn import Connection
from cats.handlers import Api, HandlerFunc, HandlerItem
from cats.middleware import Middleware, default_error_handler

__all__ = [
    'Application',
]


class Application:
    __slots__ = ('_handlers', '_middleware', '_events', '_channels')

    def __init__(self, apis: List[Api], middleware: List[Middleware] = None):
        if middleware is None:
            middleware = [
                default_error_handler,
            ]

        self._middleware = middleware
        self._events: DefaultDict[str, List[Callable]] = defaultdict(list)
        self._channels: DefaultDict[str, List[Connection]] = defaultdict(list)

        api = Api()
        for i in apis:
            api.update(i)

        self._handlers = api.compute()

    def get_handlers_by_id(self, handler_id: int) -> Optional[Union[List[HandlerItem], HandlerItem]]:
        return self._handlers.get(handler_id)

    def get_handler_id(self, handler: HandlerFunc) -> Optional[int]:
        for handler_id, handler_list in self._handlers.items():
            arr = handler_list if isinstance(handler_list, list) else [handler_list]

            for item in arr:
                if item.callback == handler:
                    return handler_id

    def channels(self) -> List[str]:
        return list(self._channels.keys())

    def channel(self, name: str) -> Iterable[Connection]:
        return (i for i in self._channels.get(name, []))

    def attach_conn_to_channel(self, conn: Connection, channel: str) -> None:
        if conn not in self._channels[channel]:
            self._channels[channel].append(conn)

    def detach_conn_from_channel(self, conn: Connection, channel: str) -> None:
        if conn in self._channels[channel]:
            self._channels[channel].remove(conn)

    def clear_channel(self, channel: str) -> None:
        self._channels[channel].clear()

    def clear_all_channels(self) -> None:
        self._channels.clear()

    def remove_conn_from_channels(self, conn: Connection) -> None:
        for channel_name in self.channels():
            self.detach_conn_from_channel(conn, channel_name)

    @property
    def middleware(self) -> Iterable[Middleware]:
        return (i for i in self._middleware)

    def add_event_listener(self, event: str, callback: Callable) -> int:
        self._events[event].append(callback)
        return id(callback)

    def remove_event_listener(self, event: str, callback: Union[int, Callable]) -> None:
        if isinstance(callback, int):
            for fn in list(self._events[event]):
                if id(fn) == callback:
                    break
            else:
                return None
        else:
            fn = callback

        if fn in self._events[event]:
            self._events[event].remove(fn)

    async def trigger(self, event: str, *args, **kwargs):
        for fn in self._events.get(event, []):
            res = fn(*args, **kwargs)
            if isawaitable(fn):
                await res
