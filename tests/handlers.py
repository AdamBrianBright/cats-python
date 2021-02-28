import os
from asyncio import sleep

from rest_framework.fields import CharField, IntegerField
from rest_framework.serializers import Serializer

from cats.codecs import Codec
from cats.server import Api, Handler, Request, Response, StreamResponse

api = Api()


@api.on(0, name='echo handler')
async def echo_handler(request: Request):
    return Response(request.data)


@api.on(1, name='no response')
async def no_response(request: Request):
    pass


class VersionedHandler(Handler, api=api, id=2, version=1):
    async def handle(self):
        return Response({'version': 1})


class VersionedHandler2(Handler, api=api, id=2, version=3, end_version=4):
    async def handle(self):
        return Response({'version': 2})


class VersionedHandler3(Handler, api=api, id=2, version=6):
    async def handle(self):
        return Response({'version': 3})


@api.on(id=0xFFFF, name='delayed response')
async def delayed_response(request: Request):
    async def gen():
        yield b'hello'
        await sleep(0.1)
        yield b' world'
        await sleep(0.1)
        yield b'!'
    return StreamResponse(gen(), Codec.T_BYTE)


@api.on(id=0xFFA0, name='internal requests')
async def internal_requests(request: Request):
    res = await request.input(b'Are you ok?')
    if res.data == b'yes':
        return Response(b'Nice!')
    else:
        return Response(b'Sad!')


@api.on(id=0xFFA1, name='internal requests')
async def internal_json_requests(request: Request):
    res = await request.input("Are you ok?")
    if res.data == "yes":
        return Response("Nice!")
    else:
        return Response("Sad!")


class JsonFormHandler(Handler, api=api, id=0xFFB0):
    class Loader(Serializer):
        id = IntegerField(min_value=0, max_value=10)
        name = CharField(min_length=3, max_length=16)

    class Dumper(Serializer):
        token = CharField(min_length=64, max_length=64)
        code = CharField(min_length=6, max_length=6)

    async def handle(self):
        user = await self.json_load()
        assert isinstance(user, dict)
        assert isinstance(user['id'], int) and 0 <= user['id'] <= 10
        assert isinstance(user['name'], str) and 3 <= len(user['name']) <= 16

        return await self.json_dump({
            'token': os.urandom(32).hex(),
            'code': os.urandom(3).hex(),
        })
