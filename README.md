# CATS

## Cifrazia Action Transport System

# Requirements

- Tornado 6+
- Python 3.8+

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
from cats import Api, Application, Event, Request, Server
from cats.middleware import default_error_handler

api = Api()


# Setup endpoint handler
@api.on(0)
async def handler(request: Request):
    return b'Hello world'


# Create app
app = Application(apis=[api], middleware=[default_error_handler])
app.add_event_listener(Event.ON_SERVER_START, lambda server: print('Hello world!'))

# Create server
cats_server = Server(app, idle_timeout=60.0, input_timeout=10.0)
cats_server.bind(9090)
cats_server.start(0)
```

# Advanced usage

## Data Types

CATS support different data types

### Binary

Code: `0x00`

- `return b'Hello world'` Byte string
- `return bytearray([1, 2, 3])` Byte array
- `return memoryview(a)` memory view
- `return bytes()` - empty payload / 0 bytes payload

### JSON

Code: `0x01`

- `return {"a": 3}` - Dict -> b`{"a":3}`
- `return [1, 2, 3]` - List -> b`[1,2,3]`
- `return 10` - Int -> b`10`
- `return 50.2` - Float -> b`50.2`
- `return False` - Bool -> b`false`
- `return cats.NULL` - null -> b`null`

### Files

Code: `0x02`

- `return Path('../app.exe')` - Single item file array -> {"app.exe": FileInfo}
- `return [Path('../file1.txt'), Path('../file2.txt)]` - File array -> {"file1.txt": FileInfo, "file2.txt": FileInfo}
- `return {"a": Path('lol.txt')}` - Named file array -> {"a": FileInfo}

### Different status

By default, "status" field is set to 200. If you want to change it you may want to create your own Request() instance
and send it manually, but if you wish to use "return" syntax you may also return `Tuple[result: Any, status: int]`

## Class handlers

If you want to describe handlers as classes - you MUST inherit them from `cats.Handler`
since it behave mostly like `@cats.handler.__call__()` decorator. If you want to inherit other parent classes, then
place `cats.Handler` at the right

```python
import cats

# CatsHandler - your custom abstract class that may add some common features
from utils import CatsHandler

api = cats.Api()


class EchoHandler(CatsHandler, cats.Handler, api=api, id=0xAFAF):
    async def handle(self):
        return self.request.data
```

## JSON validation

Packet currently support only DRF serializers

```python
import cats
from rest_framework.serializers import Serializer, IntegerField, CharField

api = cats.Api()


class UserSignIn(cats.Handler, api=api, id=0xFAFA):
    class Loader(Serializer):
        id = IntegerField()
        name = CharField(max_length=32)

    Dumper = Loader

    async def handle(self):
        data = await self.json_load()
        return await self.json_dump(data)
```

## Children request

CATS also support nested data transfer inside single handler

```python
import cats

api = cats.Api()


@api.on(1)
async def lazy_handler(request: cats.Request):
    user = request.data
    res: cats.Request = await request.input(b'Enter One-Time password')
    return {
        'username': user['username'],
        'token': 'asfbc96aecb9aeaf6aefabced',
        'code': res.data['code'],
    }


class SomeHandler(cats.Handler, id=520):
    async def handle(self):
        res = await self.input({'action': 'confirm'})
        return {'ok': True}
```

## API Versioning

You may have multiple handlers assigned to a single ID but version parameter must be provided

+ Version must be int in range 0 .. 65535 (2 bytes)
+ If you provide only base version, versions higher than current will also trigger handler
+ If you specify end version, version in range `$base` .. `$end` will trigger handler
+ If you specify base versions with gaps, then version in range `$base1` .. `$base2 - 1` will trigger handler 1

Client provide version only once at connection establishment

```python
import cats

api = cats.Api()


@api.on(1, version=0)
async def first_version(request: cats.Request):
    pass


@api.on(1, version=2, end_version=3)
async def second_version(request: cats.Request):
    pass


@api.on(1, version=5, end_version=7)
async def third_version(request: cats.Request):
    pass


@api.on(1, version=9)
async def last_version(request: cats.Request):
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

All connections are assigned to channel `__all__` and can also be assigned to different channels You can send messages
to some or every connection in channels

```python
import cats


async def handle(request: cats.Request):
    app: cats.Application = request.conn.app

    # Send to every conn in channel
    for conn in app.channel('__all__'):
        await conn.send(request.handler_id, b'Hello everybody!')

    # Add to channel
    app.attach_conn_to_channel(request.conn, 'chat #0101')

    # Remove from channel
    app.detach_conn_from_channel(request.conn, 'chat #0101')

    # Check if in channel
    if request.conn in app.channel('chat #0101'):
        pass

    # Get all channels (warning, in this example same message may be send multiple times)
    for channel in request.conn.server.channels():
        for conn in channel:
            await conn.send(0, b'Hello!', request.message_id)
```

## Events

Events allow you to mark which function to call if something happened

```python
import cats


# on handle error
async def error_handler(request: cats.Request, exc: Exception = None):
    if isinstance(exc, AssertionError):
        print(f'Assertion error occurred during handling request {request}')


app = cats.Application([])
app.add_event_listener(cats.Event.ON_HANDLE_ERROR, error_handler)
```

Supported events list:

+ `cats.Event.ON_SERVER_START [server: cats.Server]`
+ `cats.Event.ON_SERVER_CLOSE [server: cats.Server, exc: Exception = None]`
+ `cats.Event.ON_CONN_START [conn: cats.Connection]`
+ `cats.Event.ON_CONN_CLOSE [conn: cats.Connection, exc: Exception = None]`
+ `cats.Event.ON_HANDSHAKE_PASS [conn: cats.Connection]`
+ `cats.Event.ON_HANDSHAKE_FAIL [conn: cats.Connection, handshake: bytes]`
+ `cats.Event.ON_HANDLE_ERROR [request: cats.Request, exc: Exception = None]`

## Handshake

You may add handshake stage between connection and message exchange stages. To do so provide subclass instance
of `Handshake` class to the server instance:

```python
import cats

handshake = cats.SHA256TimeHandshake(b'some secret key', 1, 5.0)
server = cats.Server(cats.Application([]), handshake)
```

### `SHA256TimeHandshake(secret_key: bytes, valid_window: int, timeout: float)`

Arguments:

- `secret_key: bytes` - just a salt to generate `sha256(secret_key + time)`
- `valid_window: int >= 0` - shows how much `time` mismatch (1 = ±10 seconds) may still be valid
- `timeout: float` - how long should server wait for handshake before aborting connection

Hash arguments

- `secret_key: bytes` - key that was provided in `__init__`
- `time: int` - current unix timestamp in seconds in UTC with last digit rounded to 0. If `now = 123456789.321`
  then `time_salt = 123456780`

Client must send generated `sha256` key to server right after retrieving `8 bytes unsgined int` unix timestamp at **
connection stage**

- If handshake is valid, then nothing will be returned
- If handshake is invalid, then connection will be dropped

Handshake stage byte log example:

+ Client send `64 bytes UTF-8` of `sha256` hex digest
+ If handshake is valid: go to **Message exchange**; otherwise drop connection

# Protocol description

Protocol works over _plain_ TCP connection. All integers are in `BigEndian` format

## Connection stage

+ Client init TCP connection to server
+ Client send `4 bytes (unsigned int)` of API version
+ Server send `8 bytes (unsigned int)` of unix timestamp in milliseconds UTC

## Handshake stage

If `Handshake` subclass instance was provided to `Server` then right here client and sever must exchange messages to
establish handshake according to chosen algorithm that is described in section above.

## Message exchange

CATS only support one message at time, if you want to send different requests at same time - you can't

Message consists of 3 parts: `<Header Type>`, `<Header>` and `<Data>`

`<Header Type>` length is always `1 byte` and it shows which type of header to expect next:

**Header type `00`** - basic header

This `<Header>` length is always `20 bytes` and it consists of:

+ Handler id `2 bytes unsigned int` - treat as URI to router
+ Message id `2 bytes unsigned int` - unique (sender side generated) message ID. used to match unordered requests and
  responses
+ Status `2 bytes unsigned int` - treat as HTTP Status Code analog
+ Time `8 bytes unsigned int` - unix timestamp in milliseconds UTC - show when `.write()` was triggered at sender side
+ Data type `1 byte unsigned int` - treat as HTTP `Content-Type` header. Supported types:
  + 0x`00000000` - plain bytes
  + 0x`00000001` - JSON
  + 0x`00000002` - FILES
+ Compression type `1 byte unsigned int` - Shows if any compression was used. Supported types:
  + 0x`00000000` - no compression
  + 0x`00000001` - GZIP compression
+ Data length `4 bytes unsigned int` - Shows how long `<Data>` section is

**Header type `01`** - streaming header

This `<Header>` length is always `16 bytes` and it is same as `Header type 00` but without *Data
length* `4 bytes unsigned int`

**Header type `02`** - children request header

This `<Header>` length is always `8 bytes` and it consists of:

+ Message id `2 bytes unsigned int` - same as in request header
+ Data type `1 byte unsigned int`
+ Compression type `1 byte unsigned int`
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

**Streaming request behavior**

In this scenario instead of reading exactly `N = [0;1<<32) bytes`, where `N` defined in header, you must
read `4 bytes unsigned int` and then data in loop until `N = 0` which means end of payload

Example:

- 0x`0000000b` - ten byte chunk
- *`hello world`*
- 0x`00000001` - one byte chunk
- *`!`*
- 0x`00000000` - end of payload

Data (de)compression must be applied for each chunk separately but Codec must be applied for the entire content. So if
you wish to send JSON via Streaming request you must watch carefully how you generate it, since Codec may not support
GeneratorType data.

**Children request behavior**

If `await request.input()` was used, then before `Server calculates JSON string length` we may add any amount of
reversed request/response message exchanging but with `Header type == 02`

Example:

+ ...
+ Server reads `<Data>` with length of `26 bytes`
+ Server handler`(id=0x0000)` handles request

- ...
- Server sends `<Header type>` == `02`
- Server sends `<Header message_id=513, type=0, compress=0, length=0>` == `02 01` `00` `00` `00`
- Client reads `<Header type>` == `02`
- Client reads `<Header>`
- Client reads `<Data>` (skip since no data transferred)
- Client sends `<Header type>` == `02`
- Client sends `<Header message_id=513, type=1, compress=0, length=4` == `02 01` `01` `00` `04`
- Client sends `<Data>` == `74727565`  _(`true` json object)_
- Server reads `<Header type>` == `02`
- Server reads `<Header>`
- Server reads `<Data>`
- ...

+ Server calculates JSON string length == `17 bytes`
+ ...
