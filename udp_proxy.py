"""
UDP Chaos Proxy for BookWormHole — simulates packet loss, latency, and duplication.

Architecture:
    Client  →  Proxy  127.0.0.1:12347 (UDP)  →  Server  127.0.0.1:12349 (UDP)
                      ↑ same port the client already uses, no client changes needed

How to use:
    1. Server.py RUDP is bound to 12349, TCP stays on 12347 — just run it:
           python Server.py

    2. Run this proxy (tune chaos parameters as needed):
           python udp_proxy.py --loss 0.3 --delay 0.1 --jitter 0.05 --duplicate 0.05

    3. Start the BookWormHole client normally — select RUDP, IP = 127.0.0.1
       The client connects to 12347 as usual; the proxy intercepts and forwards.

Wireshark usage:
    - Capture on the loopback interface (lo0 on macOS)
    - All proxy traffic filter  :  udp and (udp.port == 12347 or udp.port == 12349)
    - Only DROPPED markers      :  udp and frame contains "##DROPPED##"
    - Only C→S drops            :  udp and frame contains "C>S"
    - Only S→C drops            :  udp and frame contains "S>C"
    Each DROPPED marker packet payload looks like:  ##DROPPED##|C>S|seq=42
    so you can match it against the missing seq number in the normal traffic.
"""

import argparse
import random
import socket
import struct
import threading
import time

# ── Fixed port configuration ──────────────────────────────────────────────────
PROXY_HOST   = "0.0.0.0"   # bind on all interfaces
PROXY_PORT   = 12347        # the port the client already points to
SERVER_HOST  = "127.0.0.1" # real server host
SERVER_PORT  = 12349        # real RUDP server port (TCP stays on 12347, no conflict)

# ── Wireshark marker ──────────────────────────────────────────────────────────
# Every dropped packet triggers a small UDP packet with this prefix sent back
# to whoever sent the dropped packet. Wireshark captures it as a real frame.
DROPPED_MARKER = b"##DROPPED##"

# ── Shared state ──────────────────────────────────────────────────────────────
_client_addr: tuple | None = None   # most recent client (src) address
_client_addr_lock = threading.Lock()


def _get_client_addr() -> tuple | None:
    """Thread-safe getter for the current client address."""
    with _client_addr_lock:
        return _client_addr


def _set_client_addr(addr: tuple):
    """Thread-safe setter for the current client address."""
    global _client_addr
    with _client_addr_lock:
        _client_addr = addr


def _extract_seq(data: bytes) -> int | None:
    """
    Extract the RUDP sequence number from the packet header.
    RUDP header format (protocol.py): !IIB — seq(u32), ack(u32), flags(u8) = 9 bytes.
    Returns None if the packet is too short (e.g., our own marker packets).
    """
    rudp_header_size = struct.calcsize("!IIB")  # 9 bytes
    if len(data) < rudp_header_size:
        return None
    seq_num, _, _ = struct.unpack("!IIB", data[:rudp_header_size])
    return seq_num


def _send_drop_marker(proxy_sock: socket.socket, dest: tuple,
                      original_data: bytes, direction: str):
    """
    Send a real UDP packet with the DROPPED_MARKER payload so Wireshark
    captures the drop as a visible frame.
    Payload format:  ##DROPPED##|<direction>|seq=<seq_num>
    Wireshark filter: udp and frame contains "##DROPPED##"
    """
    seq = _extract_seq(original_data)
    seq_str = str(seq) if seq is not None else "?"
    payload = DROPPED_MARKER + f"|{direction}|seq={seq_str}".encode()
    try:
        proxy_sock.sendto(payload, dest)
    except Exception:
        pass


def _apply_chaos(data: bytes, loss: float, duplicate: float) -> tuple[bool, int]:
    """
    Decide the fate of a packet.
    Returns (dropped: bool, copies: int).
    """
    if random.random() < loss:       # apply packet loss
        return True, 0
    copies = 2 if random.random() < duplicate else 1  # apply duplication
    return False, copies


def _forward(proxy_sock: socket.socket, server_sock: socket.socket,
             server_addr: tuple, loss: float, delay: float,
             jitter: float, duplicate: float):
    """
    Thread: Client → Proxy → Server.
    Listens on proxy_sock (port 12347) for packets from the client,
    applies chaos, and forwards surviving packets to server_sock (port 12349).
    """
    while True:
        try:
            data, addr = proxy_sock.recvfrom(65536)  # receive a packet from the client
        except Exception:
            continue

        if data.startswith(DROPPED_MARKER):  # ignore our own marker packets
            continue

        _set_client_addr(addr)  # remember the client address for the reverse direction

        seq = _extract_seq(data)
        dropped, copies = _apply_chaos(data, loss, duplicate)

        if dropped:
            _send_drop_marker(proxy_sock, addr, data, "C>S")  # send Wireshark-visible marker
            print(f"  ✖ [C→S] DROPPED   seq={seq}  ({len(data)}B)")
            continue

        if copies == 2:
            print(f"  ✦ [C→S] DUPLICATE seq={seq}  ({len(data)}B)")

        for copy_num in range(copies):
            wait = max(delay + random.uniform(-jitter, jitter), 0.0)
            if wait > 0:
                time.sleep(wait)
                print(f"  ⏳ [C→S] DELAY    seq={seq}  {wait:.3f}s  (copy {copy_num + 1}/{copies})")
            server_sock.sendto(data, server_addr)  # forward to the real server
            print(f"  ✔ [C→S] FORWARD  seq={seq}  ({len(data)}B)  (copy {copy_num + 1}/{copies})")


def _reverse(proxy_sock: socket.socket, server_sock: socket.socket,
             loss: float, delay: float, jitter: float, duplicate: float):
    """
    Thread: Server → Proxy → Client.
    Listens on server_sock for packets from the real server (port 12349),
    applies chaos, and forwards surviving packets back to the client via proxy_sock.
    """
    while True:
        try:
            data, _ = server_sock.recvfrom(65536)  # receive a packet from the real server
        except Exception:
            continue

        dest = _get_client_addr()
        if dest is None:  # no client seen yet, discard
            continue

        seq = _extract_seq(data)
        dropped, copies = _apply_chaos(data, loss, duplicate)

        if dropped:
            _send_drop_marker(proxy_sock, dest, data, "S>C")  # send Wireshark-visible marker
            print(f"  ✖ [S→C] DROPPED   seq={seq}  ({len(data)}B)")
            continue

        if copies == 2:
            print(f"  ✦ [S→C] DUPLICATE seq={seq}  ({len(data)}B)")

        for copy_num in range(copies):
            wait = max(delay + random.uniform(-jitter, jitter), 0.0)
            if wait > 0:
                time.sleep(wait)
                print(f"  ⏳ [S→C] DELAY    seq={seq}  {wait:.3f}s  (copy {copy_num + 1}/{copies})")
            proxy_sock.sendto(data, dest)  # forward back to the client
            print(f"  ✔ [S→C] FORWARD  seq={seq}  ({len(data)}B)  (copy {copy_num + 1}/{copies})")


def main():
    parser = argparse.ArgumentParser(
        description="UDP Chaos Proxy for BookWormHole — proxy is fixed on 127.0.0.1:12347",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--loss",      type=float, default=0.2,
                        help="Packet loss probability 0.0-1.0  (default: 0.2 = 20%%)")
    parser.add_argument("--delay",     type=float, default=0.0,
                        help="Base added latency in seconds    (default: 0.0)")
    parser.add_argument("--jitter",    type=float, default=0.0,
                        help="Random +/- latency in seconds    (default: 0.0)")
    parser.add_argument("--duplicate", type=float, default=0.0,
                        help="Duplication probability 0.0-1.0  (default: 0.0)")
    args = parser.parse_args()

    server_addr = (SERVER_HOST, SERVER_PORT)

    # Socket the client talks to — claims UDP 12347
    proxy_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    proxy_sock.bind((PROXY_HOST, PROXY_PORT))

    # Socket used to talk to the real RUDP server on 12349
    server_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    print("=" * 62)
    print("  UDP Chaos Proxy — BookWormHole")
    print("=" * 62)
    print(f"  Client connects to     :  127.0.0.1:{PROXY_PORT}  (UDP)")
    print(f"  Forwards to server     :  {SERVER_HOST}:{SERVER_PORT}  (UDP)")
    print(f"  TCP server             :  127.0.0.1:12347  (unchanged)")
    print(f"  Packet loss            :  {args.loss      * 100:.0f}%")
    print(f"  Base delay             :  {args.delay:.3f}s")
    print(f"  Jitter                 :  +/-{args.jitter:.3f}s")
    print(f"  Duplication            :  {args.duplicate * 100:.0f}%")
    print("=" * 62)
    print()
    print("  Wireshark — capture on lo0, then use these filters:")
    print(f"    All traffic  :  udp and (udp.port == {PROXY_PORT} or udp.port == {SERVER_PORT})")
    print( '    Drops only   :  udp and frame contains "##DROPPED##"')
    print( '    C->S drops   :  udp and frame contains "C>S"')
    print( '    S->C drops   :  udp and frame contains "S>C"')
    print("=" * 62)
    print()

    threading.Thread(target=_forward,
                     args=(proxy_sock, server_sock, server_addr,
                           args.loss, args.delay, args.jitter, args.duplicate),
                     daemon=True, name="C→S").start()

    threading.Thread(target=_reverse,
                     args=(proxy_sock, server_sock,
                           args.loss, args.delay, args.jitter, args.duplicate),
                     daemon=True, name="S→C").start()

    print("Proxy running. Press Ctrl+C to stop.\n")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nProxy stopped.")


if __name__ == "__main__":
    main()

