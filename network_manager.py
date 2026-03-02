import socket
import threading
from collections import deque

import protocol
import util


class NetworkManager:
    """
    Manages the server connection and implements a sliding-window
    chapter prefetch strategy (default: 2 chapters ahead).
    """

    def __init__(self, host='', port=12347, prefetch_count=2):
        self.host = host
        self.port = port
        self.prefetch_count = prefetch_count

        self.sock: socket.socket | None = None
        self.total_chapters = 0
        self.book_title = ""

        # --- Chapter Buffer ---
        # Stores received chapters: {chapter_index: chapter_text}
        self.chapter_buffer: dict[int, str] = {}
        self.next_server_index = 0
        self.current_read_index = 0
        self.book_finished = False

        # --- Threading ---
        self._lock = threading.Lock()
        self._chapter_ready = threading.Event()
        self._prefetch_thread: threading.Thread | None = None
        self._running = False

        # --- Callback for UI updates ---
        self.on_chapter_ready = None  # set by ReadPage

    def connect(self) -> bool:
        #Establish a persistent connection to the server.
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.connect((self.host, self.port))
            return True
        except Exception as e:
            print(f"Connection failed: {e}")
            return False

    def login(self, username: str, password: str) -> str:
        #Send login credentials. Returns 'SUCCESS' or 'FAIL'.
        packet = (f"{protocol.MSG_LOGIN}{protocol.SEPARATOR}"
                  f"{util.ceasar_cipher(username, 7)}{protocol.SEPARATOR}"
                  f"{util.ceasar_cipher(password, 7)}")
        protocol.send_message(self.sock, packet)
        response = protocol.recv_message(self.sock)
        return util.ceasar_decipher(response, 4)

    def request_book(self, book_title: str) -> bool:

        #Request a book from the server.
        #Receives metadata, then starts the prefetch thread.
        # Reset state
        self.chapter_buffer.clear()
        self.next_server_index = 0
        self.current_read_index = 0
        self.book_finished = False
        self.book_title = book_title

        # Send request
        msg = f"{protocol.MSG_REQUEST_BOOK}{protocol.SEPARATOR}{book_title}"
        protocol.send_message(self.sock, msg)

        # Receive metadata
        response = protocol.recv_message(self.sock)
        parts = response.split(protocol.SEPARATOR)

        if parts[0] == protocol.MSG_BOOK_META:
            self.total_chapters = int(parts[2])
            print(f"Book '{book_title}' has {self.total_chapters} chapters.")

            # Start background prefetch
            self._running = True
            self._prefetch_thread = threading.Thread(target=self._prefetch_loop, daemon=True)
            self._prefetch_thread.start()
            return True
        else:
            print(f"Error: {response}")
            return False

    def _prefetch_loop(self):
        """
        Background thread: keeps the buffer filled to `prefetch_count`
        chapters ahead of what the user is currently reading.
        """
        while self._running and not self.book_finished:
            with self._lock:
                buffered_ahead = self.next_server_index - self.current_read_index
                need_more = buffered_ahead < self.prefetch_count
                all_requested = self.next_server_index >= self.total_chapters

            if all_requested:
                # We've requested everything, wait for user to finish
                threading.Event().wait(timeout=0.1)
                continue

            if need_more:
                # Request next chapter from server
                protocol.send_message(self.sock, protocol.MSG_NEXT_CHAPTER)
                response = protocol.recv_message(self.sock)

                if not response:
                    self.book_finished = True
                    break

                parts = response.split(protocol.SEPARATOR, 2)  # max split = 2 (chapter text may contain |)

                if parts[0] == protocol.MSG_CHAPTER:
                    chapter_idx = int(parts[1])
                    chapter_text = parts[2]

                    with self._lock:
                        self.chapter_buffer[chapter_idx] = chapter_text
                        self.next_server_index = chapter_idx + 1
                        print(f"  [Prefetch] Buffered chapter {chapter_idx} "
                              f"(buffer: {self.next_server_index - self.current_read_index} ahead)")

                    # Notify UI that a chapter is ready
                    self._chapter_ready.set()
                    if self.on_chapter_ready:
                        self.on_chapter_ready(chapter_idx)

                elif parts[0] == protocol.MSG_END_OF_BOOK:
                    self.book_finished = True
                    break
            else:
                # Buffer is full, wait a bit before checking again
                threading.Event().wait(timeout=0.1)

    def get_chapter(self, index: int) -> str | None:

        #Get a chapter from the buffer.
        #Returns the text if available, None if not yet buffered.

        with self._lock:
            return self.chapter_buffer.get(index, None)

    def notify_user_advanced(self, new_read_index: int):

        #Called when the user moves to a new chapter.
        #Updates current_read_index so the prefetch thread knows it can fetch more.
        with self._lock:
            self.current_read_index = new_read_index

            # Optionally: evict old chapters to save memory
            # keys_to_remove = [k for k in self.chapter_buffer if k < new_read_index - 1]
            # for k in keys_to_remove:
            #     del self.chapter_buffer[k]

    def stop(self):
        #Stop prefetching and close the connection.
        self._running = False
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass