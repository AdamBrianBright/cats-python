class ProtocolError(OSError):
    pass


class CodecError(ValueError):
    pass


class MalformedDataError(ValueError):
    pass
