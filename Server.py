import base64
import os
import socket
import threading

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

udp_clients: dict[tuple, dict] = {}


def get_cover_base64(book: Book.Book) -> str:
    #Read a book's cover image and return it as a base64 string, or '' if none.
    if book.coverPath and os.path.exists(book.coverPath):
        with open(book.coverPath, "rb") as f:
            return base64.b64encode(f.read()).decode("ascii")
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
                username = util.ceasar_decipher(parts[1], 7)
                password = util.ceasar_decipher(parts[2], 7)

                if validate_user(username, password):
                    protocol.send_message(conn, util.ceasar_cipher("SUCCESS", 4))
                    authenticated = True
                    # Store reference to the authenticated Client object
                    for c in AllClients:
                        if c.getUserName() == username:
                            current_client_map[addr] = c
                            break
                    print(f"User '{username}' authenticated.")
                else:
                    protocol.send_message(conn, util.ceasar_cipher("FAIL", 4))

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




if __name__ == "__main__":
    type_of = "TCP"
    # type_of = "UDP"
    print(f"Starting {type_of} server...")
    if type_of == "UDP":
        start_UDP_server()
    else:
        start_TCP_server()