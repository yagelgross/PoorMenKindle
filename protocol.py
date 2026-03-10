"""
Shared protocol constants and helpers for BookWormHole client-server communication.

Message format: TYPE|FIELD1|FIELD2|...
Large messages (chapters): use length-prefixed framing.
"""
import struct


# --- Message Types ---
"""
This are all the message types that can be sent between the client and the server.
it covers the basic metadata of the book, the login, errors, mid-reading flags,
and the necessary data for the packet headers.
"""
MSG_LOGIN = "LOGIN"
MSG_REQUEST_BOOK = "REQUEST_BOOK"
MSG_NEXT_CHAPTER = "NEXT_CHAPTER"
MSG_PREV_CHAPTER = "PREV_CHAPTER"
MSG_BOOK_META = "BOOK_META"
MSG_CHAPTER = "CHAPTER"
MSG_END_OF_BOOK = "END_OF_BOOK"
MSG_ERROR = "ERROR"

# Book list
MSG_REQUEST_BOOK_LIST = "REQUEST_BOOK_LIST"
MSG_BOOK_LIST = "BOOK_LIST"
MSG_BOOK_LIST_ITEM = "BOOK_LIST_ITEM"

# Reading progress
MSG_SAVE_PROGRESS = "SAVE_PROGRESS"
MSG_GET_PROGRESS = "GET_PROGRESS"
MSG_PROGRESS = "PROGRESS"
MSG_STOP_READING = "STOP_READING"

MSG_GET_LAST_BOOK = "GET_LAST_BOOK"
MSG_LAST_BOOK = "LAST_BOOK"

# TCP headers
SEPARATOR = "|"
ENCODING = "utf-8"
HEADER_SIZE = 10  # 10-digit length header for framing


# RUDP headers
RUDP_HEADER_FORMAT = "!IIB" # the header is in big endian format, with 2 unsigned integers (sequence number and acknowledgement number) and 1 unsigned byte (flags)
RUDP_HEADER_SIZE = struct.calcsize(RUDP_HEADER_FORMAT)

# Flags for RUDP messages
RUDP_FLAG_DATA = 0x01 # istrue if this is a data packet, false if it's an ACK or SYN packet
RUDP_FLAG_ACK = 0x02 # istrue if this is an ACK packet, false if it's a data packet or SYN packet
RUDP_FLAG_SYN = 0x04 # istrue if this is a SYN packet, false if it's a data packet or ACK packet'


def build_rudp_packet(seq_num: int, ack_num: int, flags: int, payload: str) -> bytes:
    """Build a RUDP packet with the given sequence number, acknowledgement number, flags, and payload."""
    header = struct.pack(RUDP_HEADER_FORMAT, seq_num, ack_num, flags) # pack the header using the struct library
    return header + payload.encode(ENCODING) # return the packed header and payload as a bytes object

def parse_rudp_packet(packet_bytes: bytes) -> tuple[int, int, int, str]:
    """Parse a RUDP packet and return its sequence number, acknowledgement number, flags, and payload."""
    header = packet_bytes[:RUDP_HEADER_SIZE] # extract the header
    seq_num, ack_num, flags = struct.unpack(RUDP_HEADER_FORMAT, header) # unpack the header struct
    payload = packet_bytes[RUDP_HEADER_SIZE:].decode(ENCODING) # decode the payload
    return seq_num, ack_num, flags, payload # return the parsed values of the sequence number, acknowledgement number, flags, and payload


def send_message(sock, message: str):
    """Send a length-prefixed message over a socket."""
    data = message.encode(ENCODING) # encode the message as data
    header = f"{len(data):<{HEADER_SIZE}}".encode(ENCODING) # create a header with the length of the data
    sock.sendall(header + data) # send the header and data as a packet


def recv_message(sock) -> str:
    """Receive a length-prefixed message from a socket."""
    header = _recv_exact(sock, HEADER_SIZE) # receive the header using the _recv_exact method
    if not header: # if no header is received, return an empty string
        return ""
    msg_len = int(header.decode(ENCODING).strip()) # uncover the length of the header
    data = _recv_exact(sock, msg_len) # receive the data using the _recv_exact method
    if not data: # if no data is received, return an empty string
        return ""
    return data.decode(ENCODING) # decode the received data as a string and return it


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