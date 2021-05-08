from asyncio import CancelledError
from typing import Any, Callable, Optional

from tornado.iostream import StreamClosedError

from cats.server.handlers import HandlerFunc
from cats.server.request import Request
from cats.server.response import Response

__all__ = [
    'Middleware',
    'default_error_handler',
]

Middleware = Callable[[HandlerFunc, Request], Optional[Any]]


async def default_error_handler(handler: HandlerFunc, request: Request):
    try:
        return await handler(request)
    except (KeyboardInterrupt, StreamClosedError):
        raise
    except CancelledError:
        return Response(data={
            'error': 'CancelledError',
            'message': 'Request was cancelled',
        }, status=500)
    except Exception as err:
        return Response(data={
            'error': err.__class__.__name__,
            'message': str(err),
        }, status=500)
