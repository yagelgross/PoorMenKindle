import base64
import os
import socket
import threading
from PIL import Image
import io

import ebooklib
from ebooklib import epub
from bs4 import BeautifulSoup

import Client
import Book
import util
import protocol
import time

# --- Data ---
currClients: list[Client.Client] = []

availableBooks = [
    Book.Book("Eragon",      "Christopher Paolini", 50, "booksForServer/Eragon.epub",      "booksForServer/covers/Eragon.jpg"),
    Book.Book("Eldest",      "Christopher Paolini", 83, "booksForServer/Eldest.epub",       "booksForServer/covers/Eldest.png"),
    Book.Book("Brisingr",    "Christopher Paolini", 68, "booksForServer/Brisingr.epub",     "booksForServer/covers/Brisingr.png"),
    Book.Book("Inheritance", "Christopher Paolini", 88, "booksForServer/Inheritance.epub",  "booksForServer/covers/Inheritance.jpg"),
    Book.Book("אראגון", "כריסטופר פאוליני", 64, "booksForServer/אראגון.epub",      "booksForServer/covers/אראגון.jpeg"),
]

AllClients = [
    Client.Client("yagel", "123456", True),
    Client.Client("noam", "123456", True),
    Client.Client("taltul", "123456", False),
]

# Cache parsed books so we don't reparse the EPUB on every request
book_cache: dict[str, list[str]] = {}

# Maps client address → authenticated Client object (for progress tracking)
current_client_map: dict[tuple, Client.Client] = {}

# ───────── dicts for RUDP handling ─────────
# client sequence number
udp_client_seq: dict[tuple, int] = {}
# saves the packets that have yet to be acknowledged by the client, indexed by (client_addr, seq_num): {'packet': bytes, 'timestamp': float, 'retries': int}}
udp_unacked_messages: dict[tuple, dict] = {}
# manage the client's state (what book and chapter it is currently reading)
udp_client_state: dict[tuple, dict] = {}

# RUDP server logistics and functions
def get_next_seq(addr: tuple) -> int:
    """ Returns the next sequence number for a client and increments it."""
    if addr not in udp_client_seq:
        udp_client_seq[addr] = 0
    seq = udp_client_seq[addr]
    udp_client_seq[addr] += 1
    return seq


def send_rudp_reliable(server_socket: socket.socket, addr: tuple, payload: str):
    """
    Pack the payload into a RUDP packet and send it to the client. Then, add it to the unacked messages list.
    """
    seq_num = get_next_seq(addr)
    packet = protocol.build_rudp_packet(seq_num=seq_num, ack_num=0, flags=protocol.RUDP_FLAG_DATA, payload=payload)

    server_socket.sendto(packet, addr)

    # save to unacked messages if needed (for simplicity, we assume all messages require ACKs in this implementation)
    udp_unacked_messages[(addr, seq_num)] = {
        'packet': packet,
        'timestamp': time.time(),
        'retries': 0
    }


def udp_retransmission_loop(server_socket: socket.socket):
    """
    Server side background thread that handles retransmissions of unacknowledged messages.
    """
    timeout_limit = 0.5  # half a second
    max_retries = 5

    while True:
        current_time = time.time()
        # use a local list so that we do not modify the dict while iterating
        for key, info in list(udp_unacked_messages.items()):
            addr, seq_num = key

            if current_time - info['timestamp'] > timeout_limit:
                if info['retries'] < max_retries:
                    info['timestamp'] = current_time
                    info['retries'] += 1
                    server_socket.sendto(info['packet'], addr)
                    print(f"[RUDP Server] Retransmitting seq {seq_num} to {addr}")
                else:
                    print(f"[RUDP Server] Client {addr} unresponsive. Dropping packet {seq_num}")
                    del udp_unacked_messages[key]

        time.sleep(0.05)


def process_udp_request(server_socket: socket.socket, addr: tuple, payload: str):
    """
    The business side of the server. Handles login, book requests, book lists, and progress over RUDP.
    """
    parts = payload.split(protocol.SEPARATOR)
    msg_type = parts[0]

    # --- LOGIN ---
    if msg_type == protocol.MSG_LOGIN and len(parts) == 3:
        username = util.Caesar_decipher(parts[1], 7)
        password = util.Caesar_decipher(parts[2], 7)

        if validate_user(username, password):
            send_rudp_reliable(server_socket, addr, util.Caesar_cipher("SUCCESS", 4))
            udp_client_state[addr] = {'username': username, 'authenticated': True}
            print(f"[RUDP Server] User '{username}' authenticated from {addr}.")
        else:
            send_rudp_reliable(server_socket, addr, util.Caesar_cipher("FAIL", 4))
        return  # return here so it doesn't execute the rest of the function on login

    # block all other requests from unauthenticated clients
    if addr not in udp_client_state or not udp_client_state[addr].get('authenticated'):
        return

    state = udp_client_state[addr]
    username = state['username']

    # --- BOOK LIST ---
    if msg_type == protocol.MSG_REQUEST_BOOK_LIST:
        # send header: BOOK_LIST|count
        send_rudp_reliable(server_socket, addr, f"{protocol.MSG_BOOK_LIST}{protocol.SEPARATOR}{len(availableBooks)}")
        # send one BOOK_LIST_ITEM per book
        for book in availableBooks:
            cover_b64 = get_cover_base64(book)
            item = (f"{protocol.MSG_BOOK_LIST_ITEM}"
                    f"{protocol.SEPARATOR}{book.title}"
                    f"{protocol.SEPARATOR}{book.author}"
                    f"{protocol.SEPARATOR}{book.chapterCount}"
                    f"{protocol.SEPARATOR}{cover_b64}")
            send_rudp_reliable(server_socket, addr, item)
        print(f"[RUDP Server] Sent book list ({len(availableBooks)} books) to {addr}")

    # --- REQUEST BOOK ---
    elif msg_type == protocol.MSG_REQUEST_BOOK and len(parts) == 2:
        book_title = parts[1]
        chapters = epub_handler(book_title)

        if chapters is None:
            send_rudp_reliable(server_socket, addr, f"{protocol.MSG_ERROR}|Book not found")
            return

        # state metadata: what book the client is currently reading and what chapter it is on
        state['current_book'] = book_title
        state['chapter_index'] = 0

        meta = f"{protocol.MSG_BOOK_META}{protocol.SEPARATOR}{book_title}{protocol.SEPARATOR}{len(chapters)}"
        send_rudp_reliable(server_socket, addr, meta)

    # --- NEXT CHAPTER ---
    elif msg_type == protocol.MSG_NEXT_CHAPTER:
        book_title = state.get('current_book')

        # extract the specific index requested by the client (if provided)
        if len(parts) > 1:
            req_index = int(parts[1])
        else:
            req_index = state.get('chapter_index', 0)

        if not book_title:
            return

        # anti-spam mechanism: if we just sent this chapter, don't re-chunk and re-send it all at once.
        last_sent = state.get('last_sent_chapter', -1)
        if last_sent == req_index:
            return

        chapters = epub_handler(book_title)

        if chapters and req_index < len(chapters):
            chapter_text = chapters[req_index]

            # chunk up the chapter text
            most_chars = 500
            total_chunks = (len(chapter_text) + most_chars - 1) // most_chars

            for i in range(total_chunks):
                start = i * most_chars
                end = start + most_chars
                chunk_payload = f"CHUNK|{book_title}|{req_index}|{total_chunks}|{i}|{chapter_text[start:end]}"
                send_rudp_reliable(server_socket, addr, chunk_payload)

            print(f"[RUDP Server] Sent chapter {req_index} ({total_chunks} chunks) to {addr}")

            state['chapter_index'] = req_index + 1
            state['last_sent_chapter'] = req_index

        elif chapters and req_index >= len(chapters):
            send_rudp_reliable(server_socket, addr, protocol.MSG_END_OF_BOOK)

    # --- SAVE PROGRESS ---
    elif msg_type == protocol.MSG_SAVE_PROGRESS and len(parts) == 3:
        book_title = parts[1]
        chapter = int(parts[2])

        # find the client object
        client_obj = next((c for c in AllClients if c.getUserName() == username), None)
        if client_obj:
            client_obj.setCurrChapter(book_title, chapter)
            print(f"[RUDP Server] Saved progress: {username} -> {book_title} ch.{chapter}")

    # --- GET PROGRESS ---
    elif msg_type == protocol.MSG_GET_PROGRESS and len(parts) == 2:
        book_title = parts[1]
        client_obj = next((c for c in AllClients if c.getUserName() == username), None)
        chapter = -1
        if client_obj:
            chapter = client_obj.getCurrChapter(book_title)
        send_rudp_reliable(server_socket, addr, f"{protocol.MSG_PROGRESS}{protocol.SEPARATOR}{chapter}")

    # --- GET LAST BOOK ---
    elif msg_type == protocol.MSG_GET_LAST_BOOK:
        client_obj = next((c for c in AllClients if c.getUserName() == username), None)
        if client_obj and client_obj.lastBookRead:
            title = client_obj.lastBookRead
            chapter = client_obj.getCurrChapter(title)
            send_rudp_reliable(server_socket, addr,
                               f"{protocol.MSG_LAST_BOOK}{protocol.SEPARATOR}{title}{protocol.SEPARATOR}{chapter}")
        else:
            send_rudp_reliable(server_socket, addr, f"{protocol.MSG_LAST_BOOK}{protocol.SEPARATOR}NONE")


def start_UDP_server():
    """Activates the RUDP server and starts listening for incoming connections."""
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server_socket.bind(('', 12347))
    print("RUDP Server listening on port 12347...")

    # start the retransmission thread
    threading.Thread(target=udp_retransmission_loop, args=(server_socket,), daemon=True).start()

    while True:
        try:
            data, addr = server_socket.recvfrom(4096)
            # unpack the packet
            seq_num, ack_num, flags, payload = protocol.parse_rudp_packet(data)

            # if the packet is an ACK, update the unacked messages list
            if flags & protocol.RUDP_FLAG_ACK:
                key = (addr, ack_num)
                if key in udp_unacked_messages:
                    del udp_unacked_messages[key]  # delete the acknowledged packet from the unacked messages
                    print(f"[RUDP Server] Received ACK for seq {ack_num} from {addr}")
                else:
                    print(f"[RUDP Server] Received ACK for seq {ack_num} from {addr}, but no corresponding packet was unacked.")

            # if the packet is a DATA packet, process it
            if flags & protocol.RUDP_FLAG_DATA:
                # first, send an ACK to the client
                ack_packet = protocol.build_rudp_packet(seq_num=0, ack_num=seq_num, flags=protocol.RUDP_FLAG_ACK,
                                                        payload="")
                server_socket.sendto(ack_packet, addr)

                # now we can handle the client's request without worrying about retransmissions, since we've acknowledged receipt of the packet.
                # we use a background thread to handle the request so that we can continue processing other requests
                threading.Thread(target=process_udp_request, args=(server_socket, addr, payload), daemon=True).start()

        except Exception as e:
            print(f"RUDP Server Error: {e}")

# TCP server logistics and functions
def get_cover_base64(book: Book.Book) -> str:
    """ Read a book's cover image, resize it to a lightweight thumbnail, and return as base64. """
    if book.coverPath and os.path.exists(book.coverPath):
        try:
            with Image.open(book.coverPath) as img:
                # resize to thumbnail to save massive amounts of UDP bandwidth
                img.thumbnail((100, 130))

                # convert to RGB (removes alpha channel if it's a PNG) to allow JPEG compression
                if img.mode != 'RGB':
                    img = img.convert('RGB')

                buffer = io.BytesIO()
                # compress heavily into JPEG format
                img.save(buffer, format="JPEG", quality=70)

                return base64.b64encode(buffer.getvalue()).decode("ascii")
        except Exception as e:
            print(f"Error processing cover for {book.title}: {e}")
    return ""


def epub_handler(bookname: str) -> list[str] | None:
    #Parse an EPUB file and return a list of chapter texts.
    if bookname in book_cache:
        return book_cache[bookname]

    try:
        path = f"booksForServer/{bookname}.epub"
        book = epub.read_epub(path)
        chapters = []
        for item in book.get_items():
            if item.get_type() == ebooklib.ITEM_DOCUMENT:
                soup = BeautifulSoup(item.get_content(), 'html.parser')
                text = soup.get_text(separator='\n\n', strip=True)
                if text:
                    chapters.append(text)
        book_cache[bookname] = chapters
        return chapters
    except Exception as e:
        print(f"Error loading book '{bookname}': {e}")
        return None


def validate_user(username: str, password: str) -> bool:
    for client in AllClients:
        if client.getUserName() == username and client.getPassword() == password:
            if client not in currClients:
                currClients.append(client)
            return True
    return False


def handle_TCP_client(conn: socket.socket, addr):
    #Handle one client connection through login → book request → chapter streaming.
    print(f"Client connected from: {addr}")
    authenticated = False

    try:
        while True:
            raw = protocol.recv_message(conn)
            if not raw:
                print(f"Client {addr} disconnected.")
                break

            parts = raw.split(protocol.SEPARATOR)
            msg_type = parts[0]

            # ─── LOGIN ───
            if msg_type == protocol.MSG_LOGIN and len(parts) == 3:
                username = util.Caesar_decipher(parts[1], 7)
                password = util.Caesar_decipher(parts[2], 7)

                if validate_user(username, password):
                    protocol.send_message(conn, util.Caesar_cipher("SUCCESS", 4))
                    authenticated = True
                    # Store reference to the authenticated Client object
                    for c in AllClients:
                        if c.getUserName() == username:
                            current_client_map[addr] = c
                            break
                    print(f"User '{username}' authenticated.")
                else:
                    protocol.send_message(conn, util.Caesar_cipher("FAIL", 4))

            # ─── BOOK LIST ───
            elif msg_type == protocol.MSG_REQUEST_BOOK_LIST and authenticated:
                # Send header: BOOK_LIST|count
                protocol.send_message(
                    conn,
                    f"{protocol.MSG_BOOK_LIST}{protocol.SEPARATOR}{len(availableBooks)}"
                )
                # Send one BOOK_LIST_ITEM per book
                for book in availableBooks:
                    cover_b64 = get_cover_base64(book)
                    item = (f"{protocol.MSG_BOOK_LIST_ITEM}"
                            f"{protocol.SEPARATOR}{book.title}"
                            f"{protocol.SEPARATOR}{book.author}"
                            f"{protocol.SEPARATOR}{book.chapterCount}"
                            f"{protocol.SEPARATOR}{cover_b64}")
                    protocol.send_message(conn, item)
                print(f"Sent book list ({len(availableBooks)} books) to {addr}")

            # ─── REQUEST BOOK ───
            elif msg_type == protocol.MSG_REQUEST_BOOK and len(parts) == 2 and authenticated:
                book_title = parts[1]
                chapters = epub_handler(book_title)

                if chapters is None:
                    protocol.send_message(conn, f"{protocol.MSG_ERROR}|Book not found")
                    continue

                # Send metadata: total number of chapters
                meta = f"{protocol.MSG_BOOK_META}{protocol.SEPARATOR}{book_title}{protocol.SEPARATOR}{len(chapters)}"
                protocol.send_message(conn, meta)

                # Chapter-streaming loop
                chapter_index = 0
                while chapter_index < len(chapters):
                    req = protocol.recv_message(conn)
                    if not req:
                        print(f"Client {addr} disconnected during streaming.")
                        return

                    if req == protocol.MSG_NEXT_CHAPTER:
                        msg = (f"{protocol.MSG_CHAPTER}"
                               f"{protocol.SEPARATOR}{chapter_index}"
                               f"{protocol.SEPARATOR}{chapters[chapter_index]}")
                        protocol.send_message(conn, msg)
                        chapter_index += 1

                    elif req == protocol.MSG_PREV_CHAPTER:
                        if chapter_index > 0:
                            chapter_index -= 1
                            msg = (f"{protocol.MSG_CHAPTER}"
                                   f"{protocol.SEPARATOR}{chapter_index}"
                                   f"{protocol.SEPARATOR}{chapters[chapter_index]}")
                            protocol.send_message(conn, msg)

                    elif req == protocol.MSG_STOP_READING:
                        # Client wants to stop reading — exit the streaming loop
                        print(f"Client {addr} stopped reading '{book_title}' at ch.{chapter_index}")
                        break

                    elif req.startswith(protocol.MSG_SAVE_PROGRESS):
                        # Handle progress saves during streaming
                        save_parts = req.split(protocol.SEPARATOR)
                        if len(save_parts) == 3:
                            client = current_client_map.get(addr)
                            if client:
                                client.setCurrChapter(save_parts[1], int(save_parts[2]))

                    else:
                        break  # Unexpected message, exit streaming

                # Done streaming (finished or stopped) — send END_OF_BOOK
                protocol.send_message(conn, protocol.MSG_END_OF_BOOK)
                print(f"Ended streaming '{book_title}' to {addr}")

            # ─── SAVE PROGRESS ───
            elif msg_type == protocol.MSG_SAVE_PROGRESS and len(parts) == 3 and authenticated:
                book_title = parts[1]
                chapter = int(parts[2])
                client = current_client_map.get(addr)
                if client:
                    client.setCurrChapter(book_title, chapter)
                    print(f"Saved progress: {client.getUserName()} → {book_title} ch.{chapter}")

            # ─── GET PROGRESS ───
            elif msg_type == protocol.MSG_GET_PROGRESS and len(parts) == 2 and authenticated:
                book_title = parts[1]
                client = current_client_map.get(addr)
                chapter = -1
                if client:
                    chapter = client.getCurrChapter(book_title)
                protocol.send_message(
                    conn,
                    f"{protocol.MSG_PROGRESS}{protocol.SEPARATOR}{chapter}"
                )

            # ─── GET LAST BOOK ───
            elif msg_type == protocol.MSG_GET_LAST_BOOK and authenticated:
                client = current_client_map.get(addr)
                if client and client.lastBookRead:
                    title = client.lastBookRead
                    chapter = client.getCurrChapter(title)
                    protocol.send_message(
                        conn,
                        f"{protocol.MSG_LAST_BOOK}{protocol.SEPARATOR}{title}{protocol.SEPARATOR}{chapter}"
                    )
                else:
                    protocol.send_message(
                        conn,
                        f"{protocol.MSG_LAST_BOOK}{protocol.SEPARATOR}NONE"
                    )

            else:
                protocol.send_message(conn, f"{protocol.MSG_ERROR}|Unknown command")

    except Exception as e:
        print(f"Error handling client {addr}: {e}")
    finally:
        current_client_map.pop(addr, None)
        conn.close()
        print(f"Connection closed: {addr}")


def start_TCP_server():
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind(('', 12347))
    server_socket.listen(5)
    print("Server listening on port 12347...")

    while True:
        conn, addr = server_socket.accept()
        thread = threading.Thread(target=handle_TCP_client, args=(conn, addr), daemon=True)
        thread.start()




def start_server():
    print("Starting servers...")
    # start a TCP server thread
    tcp_thread = threading.Thread(target=start_TCP_server, daemon=True)
    tcp_thread.start()

    # start a RUDP server thread
    udp_thread = threading.Thread(target=start_UDP_server, daemon=True)
    udp_thread.start()

    # keep the main thread alive
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Servers shutting down...")

if __name__ == "__main__":
    start_server()