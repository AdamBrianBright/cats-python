from typing import Any, AsyncGenerator, Dict, Generator, Type, Union

from cats.headers import Headers
from cats.request import BaseRequest, Request, StreamRequest

__all__ = [
    'BaseResponse',
    'Response',
    'StreamResponse',
]


class BaseResponse:
    __slots__ = ('headers', 'data',)
    request: Type[BaseRequest]

    def __init__(self, data: Any = None, headers: Headers = None):
        if headers is not None and not isinstance(headers, dict):
            raise ValueError('Invalid headers provided')
        self.headers = headers or {}
        self.data = data

    def __init_subclass__(cls, /, request: Type[BaseRequest]):
        cls.request = request

    def request_kwargs(self) -> Dict[str, Any]:
        raise NotImplementedError


class Response(BaseResponse, request=Request):
    __slots__ = ('status',)

    def __init__(self, data: Any = None, headers: Headers = None, status: int = 200):
        self.status = status
        super().__init__(data=data, headers=headers)

    def request_kwargs(self) -> Dict[str, Any]:
        return {
            'headers': self.headers,
            'data': self.data,
            'status': self.status,
        }


class StreamResponse(Response, request=StreamRequest):
    def __init__(self, data: Union[Generator, AsyncGenerator], data_type: int,
                 headers: Headers = None, status: int = 200):
        self.data_type = data_type
        super().__init__(data=data, headers=headers, status=status)

    def request_kwargs(self) -> Dict[str, Any]:
        return {
            'headers': self.headers,
            'data': self.data,
            'data_type': self.data_type,
            'status': self.status,
        }
