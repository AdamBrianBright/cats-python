# CATS

## Cifrazia Action Transport System

# Requirements

- Tornado 6+
- Python 3.9+

# Installation

**Install via PIP**

```shell
pip install cats-python
```

**Install via Poetry**

```shell
poetry add cats-python
```

# Get Started

```python
import cats

# Create new route table
app = cats.App()


# Setup endpoint handler
@app(0)
async def handler(request: cats.Request):
    return cats.Response(b'Hello world')


# Create server

cats_server = cats.Server([app], port=9090)
cats_server.run(0)
```

# Advanced usage

## Different responses

```python
import cats

app = cats.App()


@app(id=10, name='User profile')
async def user_profile(request: cats.Request):
    return cats.JsonResponse({
        'id': 0,
        'username': 'Adam_Bright',
    })


@app(id=0xAFAA, name='Download update')
async def download_update(request: cats.Request):
    return cats.FileResponse('../tmp/app.exe')


@app(id=0xAFAB, name='Lazy download')
async def lazy_download(request: cats.Request):
    yield cats.StreamResponse(content_length=65535)
    yield b'Some plain bytes'
    yield b'other bytes part'
    # ...
```

## Class handlers

If you want to describe handlers as classes - you MUST inherit them from `app.Handler`
since it behave mostly like `@app.__call__()` decorator. If you want to inherit other parent classes, then
place `app.Handler` at the right

```python
import cats
from utils import CatsHandler

app = cats.App()


class EchoHandler(CatsHandler, app.Handler, id=0xAFAF):
    async def handle(self):
        data = self.request.data
        yield cats.Response(data)
```

## JSON validation

Packet currently support only DRF serializers

```python
import cats

app = cats.App()


class UserSignIn(app.Handler, id=0xFAFA):
    class Load(Serializer):
        id = IntegerField()
        name = CharField(max_length=32)

    Dump = Load

    async def handle(self):
        data = await self.json_load()
        return cats.JsonResponse(await self.json_dump(data))
```

## Children request

CATS also support nested data transfer inside single handler

```python
import cats

app = cats.App()


@app(1)
async def lazy_handler(request: cats.Request):
    user = request.json()
    async with request.input(b'Enter One-Time password') as res:
        return cats.JsonResponse({
            'token': 'asfbc96aecb9aeaf6aefabced'
        })


class SomeHandler(app.Handler, id=520):
    async def handle(self):
        data = self.request.data
        async with self.json_input({'action': 'confirm'}) as res:
            return cats.JsonResponse({'ok': True})
```

## API Versioning

You may have multiple handlers assigned to a single ID but version parameter must be provided

+ Version must be int in range 0 .. 65535 (2 bytes)
+ If you provide only base version, versions higher than current will also trigger handler
+ If you specify end version, version in range $base .. $end will trigger handler
+ If you specify base versions with gaps, then version in range $base1 .. $base2-1 will trigger handler 1

Client provide version only once at connection establishment

```python
import cats

app = cats.App()


@app(1, version=0)
async def first_version():
    pass


@app(1, version=2, end_version=3)
async def second_version():
    pass


@app(1, version=5, end_version=7)
async def third_version():
    pass


@app(1, version=9)
async def last_version():
    pass
```

Handlers from above will be called accordingly table below

| Conn version | Handler        |
| ------------ | -------------- |
| 0            | first_version  |
| 1            | first_version  |
| 2            | second_version |
| 3            | second_version |
| 4            | 404 Not Found  |
| 5            | third_version  |
| 6            | third_version  |
| 7            | third_version  |
| 8            | 404 Not Found  |
| 9            | last_version   |
| 10           | last_version   |
| 11           | last_version   |

## Channels

All connections are assigned to channel "__all__" and can also be assigned to different channels You can send messages
to some or every connection in channels

```python
import cats


async def handle(request: cats.Request):
    # Send to every conn in channel
    for conn in request.server.channel('__all__'):
        await conn.send(cats.Response(b'Hello everybody!'))

    # Add to channel
    request.conn.attach_to_channel('chat #0101')
    request.server.attach_conn_to_channel('chat #0101', request.conn)

    # Remove from channel
    request.conn.detach_from_channel('chat #0101')
    request.server.detach_conn_from_channel('chat #0101', request.conn)

    # Check if in channel
    request.conn in request.server.channel('chat #0101')

    # Get all channels (warning, in this example same message may be send multiple times)
    for channel in request.server.channels():
        for conn in channel:
            conn.send(cats.Response(b'Hello!'))
```

## Events

Events allow you to mark which function to call if something happened

```python
import cats.events


@cats.events.on(cats.events.HANDLE_ERROR)
async def error_handler(request: cats.Request, exc: Exception = None):
    if isinstance(exc, AssertionError):
        raise ValueError from exc
    raise exc


@cats.events.on(cats.events.BEFORE_RESPONSE)
async def global_formatter(request: cats.Request, response: cats.Response):
    if isinstance(response, JsonResponse) and response.data.get('error'):
        response.status = 500
    return response
```

Supported events list:

+ `cats.events.SERVER_START [server: cats.Server]`
+ `cats.events.SERVER_CLOSE [server: cats.Server, exc: Exception = None]`
+ `cats.events.CONN_START [conn: cats.Connection]`
+ `cats.events.CONN_CLOSE [conn: cats.Connection, exc: Exception = None]`
+ `cats.events.CONN_ERROR [conn: cats.Connection, exc: Exception = None]`
+ `cats.events.BEFORE_REQUEST [request: cats.Request] -> Optional[Request]`
+ `cats.events.AFTER_REQUEST [request: cats.Request]`
+ `cats.events.BEFORE_RESPONSE [request: cats.Request, respose: cats.Response] -> Optional[Response]`
+ `cats.events.AFTER_RESPONSE [request: cats.Request, respose: cats.Response]`
+ `cats.events.HANDLE_ERROR [request: cats.Request, exc: Exception = None] (must raise from exception)`

# Protocol description

Protocol works over _plain_ TCP connection. All integers are in `BigEndian` format

## Connection stage

+ Client init TCP connection to server
+ Client send `4 bytes (unsigned int)` of API version
+ Server send `8 bytes (unsigned int)` of unix timestamp in milliseconds UTC

## Message exchange

CATS only support one message at time, if you want to send different requests at same time - you can't

Message consists of 3 parts: `<Header Type>`, `<Header>` and `<Data>`

`<Header Type>` length is always `1 byte` and it shows which type of header to expect next:

**Header type 00** - basic header

This `<Header>` length is always `20 bytes` and it consists of:

+ Handler id `2 bytes unsigned int` - treat as URI to router
+ Message id `2 bytes unsigned int` - unique (sender side generated) message ID. used to match unordered requests and
  responses
+ Status `2 bytes unsigned int` - treat as HTTP Status Code analog
+ Time `8 bytes unsigned int` - unix timestamp in milliseconds UTC - show when `.write()` was triggered at sender side
+ Data type `1 byte unsigned int` - treat as HTTP `Content-Type` header. Supported types:
    + 00000000 - plain bytes
    + 00000001 - JSON
+ Compression type `1 byte unsigned int` - Shows if any compression was used. Supported types:
    + 00000000 - no compression
    + 00000001 - GZIP compression
+ Data length `4 bytes unsigned int` - Shows how long `<Data>` section is

**Header type 01** - children request header

This `<Header>` length is always `8 bytes` and it consists of:

+ Message id `2 bytes unsigned int` - same as in request header
+ Data type `1 byte unsigned int`
+ Compression type `1 byte unsgined int`
+ Data length `4 bytes unsigned int`

**Behavior example**

Client want to send `{"access_token": "abcdef"}` JSON string to handler `0` and receive JSON object `{"success": true}`

+ Client calculates JSON string length == `26 bytes`
+ Client checks if any compression will be of use == `no compression`
+ Client generates random number in range `0 .. 32767` == `513`
+ Client constructs `<Header>` with:
    + `Handler id = 0` == `00` `00`
    + `Message id = 513` == `02` `01`
    + `Status = 200` == `00` `C8` (in request may be anything, even `00` `00`)
    + `Time = 1608552317314`  == `00` `00` `01` `76` `85` `30` `81` `82` _12/21/2020 @ 12:05pm (UTC)_
    + `Data type = 1` == `01`
    + `Compression type = 0` == `00`
    + `Data length = 26` == `00` `00` `00` `1A`
+ Client send `<Header type>` == `00`
+ Client sends `<Header>` == `0000` `0201` `00C8` `0000017685308182` `01` `00` `0000001A`
+ Client sends `<Data>` == `7B226163636573735F746F6B656E223A2022616263646566227D`
+ Server waits for `20 bytes` of `<Header>`
+ Server reads data length from `<Header>` == `0000001A`
+ Server reads `<Data>` with length of `26 bytes`
+ Server handler`(id=0x0000)` handles request
+ Server calculates JSON string length == `17 bytes`
+ Server checks if any compression will be of use == `no compression`
+ Server constructs `<Header>` with:
    + `Handler id = 0` == `00` `00` (same as request since it is the same handler)
    + `Message id = 513` == `02 01` (same as in request since we respond and not request)
    + `Status = 200` == `00` `C8` (200 as in HTTP == Success)
    + `Time = 1608552317914`  == `00` `00` `01` `76` `85` `30` `83` `DA` _(plus 600ms)_
    + `Data type = 1` == `01`
    + `Compression type = 0` == `00`
    + `Data length = 17` == `00` `00` `00` `11`
+ Server sends `<Header type>` == `00`
+ Server sends `<Header>` == `0000` `0201` `00C8` `00000176853083DA` `01` `00` `00000011`
+ Server sends `<Data>` == `7B2273756363657373223A20747275657D`
+ Client waits for `<Header message_id=513>`
+ Client reads data length from `<Header>` == `00000011`
+ Client reads `<Data>` with length of `11 bytes`

**Children request behavior**

If `async with request.input()` was used, then before `Server calculates JSON string length` we may add any amount of
reversed request/response message exchanging but with `Header type == 01`

Example:

+ ...
+ Server reads `<Data>` with length of `26 bytes`
+ Server handler`(id=0x0000)` handles request

- ...
- Server sends `<Header type>` == `01`
- Server sends `<Header message_id=513, type=0, compress=0, length=0>` == `02 01` `00` `00` `00`
- Client reads `<Header type>` == `01`
- Client reads `<Header>`
- Client reads `<Data>` (skip since no data transferred)
- Client sends `<Header type>` == `01`
- Client sends `<Header message_id=513, type=1, compress=0, length=4` == `02 01` `01` `00` `04`
- Client sends `<Data>` == `74727565`  _(`true` json object)_
- Server reads `<Header type>` == `01`
- Server reads `<Header>`
- Server reads `<Data>`
- ...

+ Server calculates JSON string length == `17 bytes`
+ ...