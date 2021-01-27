from asyncio import CancelledError
from typing import Any, Callable, Optional

from tornado.iostream import StreamClosedError

from cats.handlers import HandlerFunc
from cats.request import Request

__all__ = [
    'Middleware',
    'default_error_handler',
]

Middleware = Callable[[HandlerFunc, Request], Optional[Any]]


async def default_error_handler(handler: HandlerFunc, request: Request):
    try:
        return await handler(request)
    except (KeyboardInterrupt, StreamClosedError, CancelledError):
        raise
    except Exception as err:
        return {
                   'error': err.__class__.__name__,
                   'message': str(err),
               }, 500