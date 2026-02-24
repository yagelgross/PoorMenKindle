"""
Shared protocol constants and helpers for BookWormHole client-server communication.

Message format: TYPE|FIELD1|FIELD2|...
Large messages (chapters): use length-prefixed framing.
"""

# --- Message Types ---
MSG_LOGIN = "LOGIN"
MSG_REQUEST_BOOK = "REQUEST_BOOK"
MSG_NEXT_CHAPTER = "NEXT_CHAPTER"
MSG_BOOK_META = "BOOK_META"
MSG_CHAPTER = "CHAPTER"
MSG_END_OF_BOOK = "END_OF_BOOK"
MSG_ERROR = "ERROR"

SEPARATOR = "|"
ENCODING = "utf-8"
HEADER_SIZE = 10  # 10-digit length header for framing


def send_message(sock, message: str):
    """Send a length-prefixed message over a socket."""
    data = message.encode(ENCODING)
    header = f"{len(data):<{HEADER_SIZE}}".encode(ENCODING)
    sock.sendall(header + data)


def recv_message(sock) -> str:
    """Receive a length-prefixed message from a socket."""
    header = _recv_exact(sock, HEADER_SIZE)
    if not header:
        return ""
    msg_len = int(header.decode(ENCODING).strip())
    data = _recv_exact(sock, msg_len)
    if not data:
        return ""
    return data.decode(ENCODING)


def _recv_exact(sock, num_bytes: int) -> bytes:
    """Receive exactly num_bytes from socket."""
    chunks = []
    received = 0
    while received < num_bytes:
        chunk = sock.recv(min(4096, num_bytes - received))
        if not chunk:
            return b""
        chunks.append(chunk)
        received += len(chunk)
    return b"".join(chunks)