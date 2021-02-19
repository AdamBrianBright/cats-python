class Event:
    ON_SERVER_START = 'on_server_start'  # Server
    ON_SERVER_SHUTDOWN = 'on_server_shutdown'  # Server, Exception?
    ON_HANDSHAKE_PASS = 'on_handshake_pass'  # Server, Connection
    ON_HANDSHAKE_FAIL = 'on_handshake_fail'  # Server, Connection, bytes
    ON_CONN_START = 'on_conn_start'  # Server, Connection
    ON_CONN_CLOSE = 'on_conn_close'  # Server, Connection, Exception?
    ON_HANDLE_ERROR = 'on_handle_error'  # Request, Exception?
