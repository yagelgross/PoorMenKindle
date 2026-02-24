import socket
import threading

import ebooklib
from ebooklib import epub
from bs4 import BeautifulSoup

import Client
import Book
import util
import protocol

# --- Data ---
currClients: list[Client.Client] = []

availableBooks = [
    Book.Book("Eragon", "Cristopher Paolini", 50, "booksForServer/Eragon.epub"),
    Book.Book("Eldest", "Cristopher Paolini", 83, "booksForServer/Eldest.epub"),
    Book.Book("Brisingr", "Cristopher Paolini", 68, "booksForServer/Brisingr.epub"),
    Book.Book("Inheritance", "Cristopher Paolini", 88, "booksForServer/Inheritance.epub"),
]

AllClients = [
    Client.Client("yagel", "123456", True),
    Client.Client("noam", "123456", True),
    Client.Client("taltul", "123456", False),
]

# Cache parsed books so we don't re-parse the EPUB on every request
book_cache: dict[str, list[str]] = {}


def epub_handler(bookname: str) -> list[str] | None:
    """Parse an EPUB file and return a list of chapter texts."""
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


def handle_client(conn: socket.socket, addr):
    """Handle one client connection through login → book request → chapter streaming."""
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
                    print(f"User '{username}' authenticated.")
                else:
                    protocol.send_message(conn, util.ceasar_cipher("FAIL", 4))

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

                # Now enter the chapter-streaming loop:
                # Wait for NEXT_CHAPTER requests and send one chapter at a time.
                # The CLIENT controls pacing (only requests when buffer < 2).
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
                    else:
                        break  # Unexpected message, exit streaming

                # All chapters sent
                protocol.send_message(conn, protocol.MSG_END_OF_BOOK)
                print(f"Finished streaming '{book_title}' to {addr}")

            else:
                protocol.send_message(conn, f"{protocol.MSG_ERROR}|Unknown command")

    except Exception as e:
        print(f"Error handling client {addr}: {e}")
    finally:
        conn.close()
        print(f"Connection closed: {addr}")


def start_server():
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind(('', 12347))
    server_socket.listen(5)
    print("Server listening on port 12347...")

    while True:
        conn, addr = server_socket.accept()
        # Each client gets its own thread
        thread = threading.Thread(target=handle_client, args=(conn, addr), daemon=True)
        thread.start()


if __name__ == "__main__":
    start_server()