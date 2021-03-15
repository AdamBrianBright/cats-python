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
from cats import Event
from cats.server import Api, Application, Request, Server, Response
from cats.server.middleware import default_error_handler

api = Api()


# Setup endpoint handler
@api.on(0)
async def handler(request: Request):
    return Response(b'Hello world')


# Create app
app = Application(apis=[api], middleware=[default_error_handler], idle_timeout=60.0, input_timeout=10.0)
app.add_event_listener(Event.ON_SERVER_START, lambda server: print('Hello world!'))

# Create server
cats_server = Server(app)
cats_server.bind(9090)
cats_server.start(0)
```

# Advanced usage

## Data Types

CATS support different data types

### Binary

Code: `0x00`

- `Response(b'Hello world')` Byte string
- `Response(bytearray([1, 2, 3]))` Byte array
- `Response(memoryview(a))` memory view
- `Response(bytes())` - empty payload / 0 bytes payload

### JSON

Code: `0x01`

- `Response({"a": 3})` - Dict -> b`{"a":3}`
- `Response([1, 2, 3])` - List -> b`[1,2,3]`
- `Response(10)` - Int -> b`10`
- `Response(50.2)` - Float -> b`50.2`
- `Response(False)` - Bool -> b`false`
- `Response(cats.NULL)` - null -> b`null`

### Files

Code: `0x02`

- `Response(Path('../app.exe'))` - Single item file array -> {"app.exe": FileInfo}
- `Response([Path('../file1.txt'), Path('../file2.txt)])` - File array -> {"file1.txt": FileInfo, "file2.txt": FileInfo}
- `Response({"a": Path('lol.txt')})` - Named file array -> {"a": FileInfo}

### Different status

By default, response "status" field is set to 200. You may change it like this `return Response(data, status=500)`

## Class handlers

If you want to describe handlers as classes - you MUST inherit them from `cats.Handler`
since it behave mostly like `@cats.handler.__call__()` decorator. If you want to inherit other parent classes, then
place `cats.Handler` at the right

```python
from cats.server import Api, Handler, Response

# CatsHandler - your custom abstract class that may add some common features
from utils import CatsHandler

api = Api()


class EchoHandler(CatsHandler, Handler, api=api, id=0xAFAF):
  async def handle(self):
    return Response(self.request.data)
```

## JSON validation

Packet currently support only DRF serializers.

> _Notice!_ json_dump is also an alias for `Response` creation

```python
from cats.server import Api, Handler
from rest_framework.serializers import Serializer, IntegerField, CharField

api = Api()


class UserSignIn(Handler, api=api, id=0xFAFA):
  class Loader(Serializer):
    id = IntegerField()
    name = CharField(max_length=32)

  Dumper = Loader

  async def handle(self):
    data = await self.json_load(many=False)
    return await self.json_dump(data, headers={'Reason': 'Echo'}, status=301, many=False)
```

## Children request

CATS also support nested data transfer inside single handler

```python
from cats.server import Api, Request, InputRequest, Response, Handler

api = Api()


@api.on(1)
async def lazy_handler(request: Request):
  user = request.data
  res: InputRequest = await request.input(b'Enter One-Time password')
  return Response({
    'username': user['username'],
    'token': 'asfbc96aecb9aeaf6aefabced',
    'code': res.data['code'],
  })


class SomeHandler(Handler, api=api, id=520):
  async def handle(self):
    res = await self.input({'action': 'confirm'})
    return Response({'ok': True})
```

## API Versioning

You may have multiple handlers assigned to a single ID but version parameter must be provided

+ Version must be int in range 0 .. 65535 (2 bytes)
+ If you provide only base version, versions higher than current will also trigger handler
+ If you specify end version, version in range `$base` .. `$end` will trigger handler
+ If you specify base versions with gaps, then version in range `$base1` .. `$base2 - 1` will trigger handler 1

Client provide version only once at connection establishment

```python
from cats.server import Api, Request

api = Api()


@api.on(1, version=0)
async def first_version(request: Request):
  pass


@api.on(1, version=2, end_version=3)
async def second_version(request: Request):
  pass


@api.on(1, version=5, end_version=7)
async def third_version(request: Request):
  pass


@api.on(1, version=9)
async def last_version(request: Request):
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
from cats.server import Request, Connection, Application


async def handle(request: Request):
  conn: Connection = request.conn
  app: Application = conn.app

  # Send to every conn in channel
  for conn in app.channel('__all__'):
    await conn.send(request.handler_id, b'Hello everybody!')

  # Add to channel
  app.attach_conn_to_channel(request.conn, 'chat #0101')
  conn.attach_to_channel('chat #0101')

  # Remove from channel
    app.detach_conn_from_channel(request.conn, 'chat #0101')
    conn.detach_from_channel('chat #0101')

    # Check if in channel
    if request.conn in app.channel('chat #0101'):
        pass

    # Get all channels (warning, in this example same message may be send multiple times)
    for channel in app.channels():
      for conn in app.channel(channel):
        await conn.send(0, b'Hello!', message_id=request.message_id)
```

## Events

Events allow you to mark which function to call if something happened

```python
from cats import Event
from cats.server import Request, Application


# on handle error
async def error_handler(request: Request, exc: Exception = None):
  if isinstance(exc, AssertionError):
    print(f'Assertion error occurred during handling request {request}')


app = Application([])
app.add_event_listener(Event.ON_HANDLE_ERROR, error_handler)
```

Supported events list:

+ `cats.Event.ON_SERVER_START [server: cats.Server]`
+ `cats.Event.ON_SERVER_CLOSE [server: cats.Server, exc: Exception = None]`
+ `cats.Event.ON_CONN_START [server: cats.Server, conn: cats.Connection]`
+ `cats.Event.ON_CONN_CLOSE [server: cats.Server, conn: cats.Connection, exc: Exception = None]`
+ `cats.Event.ON_HANDSHAKE_PASS [server: cats.Server, conn: cats.Connection]`
+ `cats.Event.ON_HANDSHAKE_FAIL [server: cats.Server, conn: cats.Connection, handshake: bytes]`
+ `cats.Event.ON_HANDLE_ERROR [request: cats.Request, exc: Exception = None]`

## Handshake

You may add handshake stage between connection and message exchange stages. To do so provide subclass instance
of `Handshake` class to the server instance:

```python
from cats.server import Application, Server
from cats.handshake import SHA256TimeHandshake

handshake = SHA256TimeHandshake(b'some secret key', 1, 5.0)
server = Server(Application([]), handshake)
```

If failed, handshake must raise `cats.handshake.HandshakeError` exception

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

- If handshake is valid, `01` will be returned
- If handshake is invalid, `00` will be returned and connection will be dropped

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

### Message structure

Message consists of 4 parts: `<Header Type>`, `<Header>`, `<Message Header>` and `<Data>`

`<Header Type>` length is always `1 byte` and it shows which type of header to expect next:

### Header types

**Header type `00`** - basic header

This `<Header>` length is always `18 bytes` and it consists of:

+ Handler id `2 bytes unsigned int` - treat as URI to router
+ Message id `2 bytes unsigned int` - unique (sender side generated) message ID. used to match unordered requests and
  responses
+ Time `8 bytes unsigned int` - unix timestamp in milliseconds UTC - show when `.write()` was triggered at sender side
+ Data type `1 byte unsigned int` - treat as HTTP `Content-Type` header. Supported types:
  + 0x`00000000` - plain bytes
  + 0x`00000001` - JSON
  + 0x`00000002` - FILES
+ Compression type `1 byte unsigned int` - Shows if any compression was used. Supported types:
  + 0x`00000000` - no compression
  + 0x`00000001` - GZIP compression
+ Data length `4 bytes unsigned int` - Shows how long `<Message Header>` + `2 empty bytes` + `<Data>` sections are

**Header type `01`** - streaming header

This `<Header>` length is always `14 bytes` and it is same as `Header type 00` but without *Data length*
`4 bytes unsigned int`

`<Message Header>` here shows as a first chunk _(learn about chunks below)_

**Header type `02`** - children request header

This `<Header>` length is always `8 bytes` and it consists of:

+ Message id `2 bytes unsigned int` - same as in request header
+ Data type `1 byte unsigned int`
+ Compression type `1 byte unsigned int`
+ Data length `4 bytes unsigned int` - Shows how long `<Message Header>` + `2 empty bytes` + `<Data>` sections are

### Message header

Message header works like in HTTP: It contains META information that can be used at protocol level to change up server
behavior w/o changing business logic.

Message header is a simple `UTF-8` encoded JSON dictionary followed by two empty bytes (`\x00\x00`)

**Request only Headers**

- `"Offset": int` [1] - tells the server to skip N amount of first bytes of `<Data>` section

**Response only Headers**

There are no response-only header currently supported

**Common Headers**

- `"Files": [{"key": str, "name": str, "size": int, "type": str?}]` [1] - This header is being used when `<Data Type>`
  in packet header is set to `FILES - 0x02`
- `"Status": int` - HTTP Status code analog. Usually only used by a server to show client if there was any error or not.

> [1] Using "Offset" header for the handler that returns `FILES` will also decrease "size" fields in "Files" response header.
> If "size" will drop to zero, then file won't appear in "Files" header.

## Behavior example

### Basic behavior

Client wants to send `{"access_token": "abcdef"}` JSON string to handler `0` and receive JSON object `{"success": true}`
Client wants to send no headers - therefore empty JSON `{}`

+ Client encodes `<Message Header>` into `UTF-8 Json Dict`, then adds two empty bytes == `7B 7D 00 00`
+ Client calculates JSON string length == `26 bytes`, then adds `<Message Header>` length == `30 bytes`
+ Client checks if any compression will be of use == `no compression`
+ Client generates random number in range `0 .. 32767` == `513`
+ Client constructs `<Header>` with:
  + `Handler id = 0` == `00` `00`
  + `Message id = 513` == `02` `01`
  + `Time = 1608552317314`  == `00` `00` `01` `76` `85` `30` `81` `82` _12/21/2020 @ 12:05pm (UTC)_
  + `Data type = 1` == `01`
  + `Compression type = 0` == `00`
  + `Data length = 30` == `00` `00` `00` `1E`
+ Client send `<Header type>` == `00`
+ Client sends `<Header>` == `0000` `0201` `0000017685308182` `01` `00` `0000001E`
+ Client sends `<Message Header>` == `7B7D` `0000`
+ Client sends `<Data>` == `7B226163636573735F746F6B656E223A2022616263646566227D`
+ Server waits for `18 bytes` of `<Header>`
+ Server reads data length from `<Header>` == `0000001E`
+ Server reads `<Payload>` with length of `30 bytes`
+ Server splits `<Payload>` onto `<Message Header>` and `<Data>` using `00 00` _(two empty bytes)_ separator
+ Server handler`(id=0x0000)` handles request
+ Server constructs `<Message Header>` == `7B 7D 00 00`
+ Server calculates JSON string length == `17 bytes` + `4 bytes` == `21 bytes`
+ Server checks if any compression will be of use == `no compression`
+ Server constructs `<Header>` with:
  + `Handler id = 0` == `00` `00` (same as request since it is the same handler)
  + `Message id = 513` == `02 01` (same as in request since we respond and not request)
  + `Time = 1608552317914`  == `00` `00` `01` `76` `85` `30` `83` `DA` _(plus 600ms)_
  + `Data type = 1` == `01`
  + `Compression type = 0` == `00`
  + `Data length = 17` == `00` `00` `00` `15`
+ Server sends `<Header type>` == `00`
+ Server sends `<Header>` == `0000` `0201` `00000176853083DA` `01` `00` `00000015`
+ Server sends `<Message Header>` == `7B7D` `0000`
+ Server sends `<Data>` == `7B2273756363657373223A20747275657D`
+ Client waits for `<Header message_id=513>`
+ Client reads data length from `<Header>` == `00000011`
+ Client reads `<Message Header>` and `<Data>` with length of `17 bytes`

### Streaming request behavior

**In comparison with basic behavior**

In this scenario instead of reading exactly `N = [0;1<<32) bytes`, where `N` defined in `<Header>`, you must
read `4 bytes unsigned int` and then data in loop until `N = 0` which means end of payload

**Headers**

Sender must include `<Message Header>` _(without two empty bytes)_ as first chunk of payload. Therefore, no matter how
empty payload actually is, first `4 bytes` of length and chunk must contain at least:

- `00 00 00 02` - Chunk length
- `7B 7D` - Message Header

**Compression**

Data (de)compression must be applied for each chunk separately but Codec must be applied for the entire content. So if
you wish to send JSON via Streaming request you must watch carefully how you generate it, since Codec may not support
GeneratorType data.

**Payload Example:**

- 0x`00000002` - two byte chunk
- *`{}` - Empty message Header
- 0x`0000000b` - ten byte chunk
- *`hello world`*
- 0x`00000001` - one byte chunk
- *`!`*
- 0x`00000000` - end of payload

This will be parsed as:

- `<Message Header>` == `{}`
- `<Data>` == `"hello world!""`

### Children request behavior

If `await request.input()` was used, then before `Server calculates JSON string length` we may add any amount of
reversed request/response message exchanging but with `Header type == 02`

Example:

+ ...
+ Server reads `<Data>` with length of `26 bytes`
+ Server handler`(id=0x0000)` handles request

- ...
- Server sends `<Header type>` == `02`
- Server sends `<Header message_id=513, type=0, compress=0, length=4>` == `02 01` `00` `00` `00 00 00 04`
- Server sends `<Message Header>` == `7B 7D 00 00`
- Client reads `<Header type>` == `02`
- Client reads `<Header>`
- Client reads `<Message Header>` == `{}` + two empty bytes as separator
- Client reads `<Data>` (skip since no data transferred)
- Client sends `<Header type>` == `02`
- Client sends `<Header message_id=513, type=1, compress=0, length=8` == `02 01` `01` `00` `00 00 00 08`
- Client sends `<Message Header>` == `7B 7D 00 00`
- Client sends `<Data>` == `74727565`  _(`true` json object)_
- Server reads `<Header type>` == `02`
- Server reads `<Header>`
- Server reads `<Message Header>`
- Server reads `<Data>`
- ...

+ Server calculates JSON string length == `17 bytes` + `4 bytes` message header _(including two empty bytes)_
+ ...

## Speed Limiter

If client wants to limit download speed it must send `05` _(header type 5)_ and `4 bytes unsigned int` - the amount of
bytes per seconds.

- The default speed limit for connection: 1 << 25 (32 MB).
- If you send `00 00 00 00` - there will be no speed limit.
- Speed limit must be `0` or in range `1KB - 32MB` \[1024 .. 33_554_432 bytes\]
