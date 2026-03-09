import socket
import threading
import protocol
import util
from collections import deque
from RUDPHandle import ChapterAssembler




class NetworkManager:
    """
    Manages the server connection and implements a sliding-window
    chapter prefetch strategy (default: 2 chapters ahead).
    """

    def __init__(self, host='', port=12347, prefetch_count=2, type: str = "TCP"):
        self.type = type
        self.host = host
        self.port = port
        self.prefetch_count = prefetch_count

        if self.type == "TCP":
            self.sock: socket.socket | None = None
        elif self.type == "RUDP":
            self.server_addr = (self.host, self.port)
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.assembler = ChapterAssembler()

        self.total_chapters = 0
        self.book_title = ""

        # --- Chapter Buffer ---
        # Stores received chapters: {chapter_index: chapter_text}
        self.chapter_buffer: dict[int, str] = {}
        self.next_server_index = 0
        self.current_read_index = 0
        self.book_finished = False

        # --- Threading primitives ---
        self._lock = threading.Lock()
        self._chapter_ready = threading.Event()
        self._prefetch_thread: threading.Thread | None = None
        self._running = False

        # --- Callback for UI updates ---
        self.on_chapter_ready = None  # set by ReadPage

        # --- Synchronization for RUDP ---
        self.server_response_payload = ""
        self.server_response_event = threading.Event()
        self.book_list_buffer = []
        self.streaming = False

    def TCP_connect(self) -> bool:
        """ Establish a stable and persistent TCP connection to the server."""
        #Establish a persistent connection to the server.
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.connect((self.host, self.port))
            return True
        except Exception as e:
            print(f"Connection failed: {e}")
            return False

    def RUDP_connect(self) -> bool:
        """ Connect to the server using RUDP."""
        self._running = True
        threading.Thread(target=self._rudp_listen_loop, daemon=True).start()
        return True

    def TCP_login(self, username: str, password: str) -> str:
        #Send login credentials. Returns 'SUCCESS' or 'FAIL'.
        packet = (f"{protocol.MSG_LOGIN}{protocol.SEPARATOR}"
                  f"{util.ceasar_cipher(username, protocol.LOGIN_SHIFT)}{protocol.SEPARATOR}"
                  f"{util.ceasar_cipher(password, protocol.LOGIN_SHIFT)}")
        protocol.send_message(self.sock, packet)
        response = protocol.recv_message(self.sock)
        return util.ceasar_decipher(response, protocol.RESPONSE_SHIFT)

    def RUDP_login(self, username: str, password: str) -> str:
        """ Creates and sends a RUDP login packet securely using the listen loop. """
        # preparing the payload for the RUDP packet
        payload = (f"{protocol.MSG_LOGIN}{protocol.SEPARATOR}"
                   f"{util.ceasar_cipher(username, protocol.LOGIN_SHIFT)}{protocol.SEPARATOR}"
                   f"{util.ceasar_cipher(password, protocol.LOGIN_SHIFT)}")
        # packing the RUDP packet (header + payload)
        packet = protocol.build_rudp_packet(seq_num=0, ack_num=0, flags=protocol.RUDP_FLAG_DATA, payload=payload)

        # define reliability parameters
        max_retries = 3

        for attempt in range(max_retries):
            self.server_response_event.clear()  # reset the event before sending

            # transmit the packet
            self.sock.sendto(packet, self.server_addr)

            # wait for the main loop to catch the response and set the event
            if self.server_response_event.wait(timeout=2.0):
                # decipher the response
                return util.ceasar_decipher(self.server_response_payload, protocol.RESPONSE_SHIFT)

            print(f"Login attempt {attempt + 1} timed out. Retrying...")

        # if we reach here, it means we've tried and failed
        return "FAIL"

    def TCP_request_book(self, book_title: str) -> bool:
        """ Request a book from the server using TCP."""
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
            self.streaming = True #we have begun reading a book
            self._running = True
            self._prefetch_thread = threading.Thread(target=self._TCP_prefetch_loop, daemon=True)
            self._prefetch_thread.start()
            return True
        else:
            print(f"Error: {response}")
            return False

    def RUDP_request_book(self, book_title: str) -> bool:
        """ Request a book from the server using RUDP and start the prefetch loop. """
        self.chapter_buffer.clear()
        self.next_server_index = 0
        self.current_read_index = 0
        self.book_finished = False
        self.book_title = book_title

        # preparing the RUDP packet
        payload = f"{protocol.MSG_REQUEST_BOOK}{protocol.SEPARATOR}{book_title}"
        packet = protocol.build_rudp_packet(seq_num=0, ack_num=0, flags=protocol.RUDP_FLAG_DATA, payload=payload)

        # define reliability parameters
        max_retries = 3

        for attempt in range(max_retries):
            self.server_response_event.clear()
            self.sock.sendto(packet, self.server_addr)

            # wait for the server's response via the listen loop
            if self.server_response_event.wait(timeout=2.0):
                parts = self.server_response_payload.split(protocol.SEPARATOR)
                if parts[0] == protocol.MSG_BOOK_META:
                    self.total_chapters = int(parts[2])
                    print(f"Book '{book_title}' has {self.total_chapters} chapters.")

                    # Start background prefetch
                    self.streaming = True #we have begun reading a book
                    self._running = True
                    self._prefetch_thread = threading.Thread(target=self._rudp_prefetch_loop, daemon=True)
                    self._prefetch_thread.start()
                    return True

            print(f"Request book attempt {attempt + 1} timed out. Retrying...")

        return False

    def _rudp_listen_loop(self):
        """
        A background thread that continuously listens for incoming RUDP packets from the server,
        processes them, assembles chapters, and wakes up waiting functions.
        """
        # set a fixed timeout to prevent Errno 35 and allow graceful exit
        self.sock.settimeout(1.0)

        while self._running:
            try:
                # receiving a UDP packet
                data, addr = self.sock.recvfrom(65536)
            except (socket.timeout, BlockingIOError):
                continue  # normal behavior, keep listening
            except Exception as e:
                if self._running:
                    print(f"UDP Listen Loop Error: {e}")
                continue

            try:
                # unpacking the RUDP packet using the protocol class
                seq_num, ack_num, flags, payload = protocol.parse_rudp_packet(data)

                # if it is a data packet, send an ACK
                if flags & protocol.RUDP_FLAG_DATA:
                    ack_packet = protocol.build_rudp_packet(seq_num=0, ack_num=seq_num, flags=protocol.RUDP_FLAG_ACK,
                                                            payload="")
                    self.sock.sendto(ack_packet, self.server_addr)

                    # assemble the chapter from the received chunks
                    if payload.startswith("CHUNK|"):
                        result = self.assembler.receive_chunk(payload)

                        # unpack the tuple!
                        if result:
                            chap_idx, assembled_text = result
                            with self._lock:
                                self.chapter_buffer[chap_idx] = assembled_text
                                self.next_server_index = chap_idx + 1
                                print(f"[RUDP] Successfully assembled chapter {chap_idx}")

                            # update the UI with the new chapter
                            self._chapter_ready.set()
                            if self.on_chapter_ready:
                                self.on_chapter_ready(chap_idx)
                    else:
                    # catch book list items separately
                        if payload.startswith(protocol.MSG_BOOK_LIST_ITEM):
                            self.book_list_buffer.append(payload)
                        else:
                            # if it's not a chunk or a list item, it's LOGIN SUCCESS, BOOK_META, or BOOK_LIST header
                            self.server_response_payload = payload
                            self.server_response_event.set()

                            if payload == protocol.MSG_END_OF_BOOK:
                                self.book_finished = True

            except Exception as e:
                print(f"Packet processing error: {e}")

    def _TCP_prefetch_loop(self):
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
                # We've requested everything, wait for the user to finish
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

    def _rudp_prefetch_loop(self):
        """
        Background thread: keeps the buffer filled to `prefetch_count`
        chapters ahead of what the user is currently reading, using RUDP.
        """
        while self._running and not self.book_finished:
            with self._lock:
                buffered_ahead = self.next_server_index - self.current_read_index
                need_more = buffered_ahead < self.prefetch_count
                all_requested = self.next_server_index >= self.total_chapters

            if all_requested:
                threading.Event().wait(timeout=0.1)
                continue

            if need_more:
                # request the specific next chapter from the server
                payload = f"{protocol.MSG_NEXT_CHAPTER}{protocol.SEPARATOR}{self.next_server_index}"
                packet = protocol.build_rudp_packet(seq_num=0, ack_num=0, flags=protocol.RUDP_FLAG_DATA,
                                                    payload=payload)
                self.sock.sendto(packet, self.server_addr)

                # save the current index for comparison
                expected_index = self.next_server_index

                # wait for the server to send the next chapter.
                # increased timeout to prevent spamming the server if UDP is slow
                timeout_counter = 0
                max_wait_cycles = 50  # max 5 seconds of waiting

                while self._running and self.next_server_index == expected_index and timeout_counter < max_wait_cycles:
                    threading.Event().wait(timeout=0.1)
                    timeout_counter += 1

                if self.next_server_index > expected_index:
                    # everything is good, update the buffer
                    pass
                else:
                    print(f"[RUDP] Timeout waiting for chapter {expected_index}. Re-requesting...")
            else:
                # full buffer, wait a bit before checking again
                threading.Event().wait(timeout=0.1)

    def get_chapter(self, index: int) -> str | None:
        """
        Get a chapter from the buffer.
        Returns the text if available, None if not yet buffered.
        """
        with self._lock:
            return self.chapter_buffer.get(index, None)

    def notify_user_advanced(self, new_read_index: int):
        """
        Called when the user moves to a new chapter.
        Updates current_read_index so the prefetch thread knows it can fetch more.
        """
        with self._lock:
            self.current_read_index = new_read_index

            # Optionally: evict old chapters to save memory
            #keys_to_remove = [k for k in self.chapter_buffer if k < new_read_index - 1]
            #for k in keys_to_remove:
                #del self.chapter_buffer[k]

    def stop(self):
        #Stop prefetching and close the connection.
        self._running = False
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass

    def connect(self) -> bool:
        if self.type == "TCP":
            return self.TCP_connect()
        else:
            return self.RUDP_connect()

    def login(self, username: str, password: str) -> str:
        if self.type == "TCP":
            return self.TCP_login(username, password)
        else:
            return self.RUDP_login(username, password)

    def request_book(self, book_title: str) -> bool:
        if self.type == "TCP":
            return self.TCP_request_book(book_title)
        else:
            return self.RUDP_request_book(book_title)

    # ==================== READING PROGRESS & CONTROL ====================

    def stop_prefetch(self):
        """ stop the prefetch thread without killing the rudp listen loop """
        # we use book_finished to stop the prefetch loop instead of _running
        self.book_finished = True

        if self._prefetch_thread:
            self._prefetch_thread.join(timeout=1.0)
            self._prefetch_thread = None

    def save_progress(self, book_title: str, chapter_index: int):
        """ Tell the server to save reading progress for the current user. (Fire and forget) """
        if self.type == "TCP":
            msg = f"{protocol.MSG_SAVE_PROGRESS}{protocol.SEPARATOR}{book_title}{protocol.SEPARATOR}{chapter_index}"
            try:
                protocol.send_message(self.sock, msg)
            except Exception:
                pass
        else:
            payload = f"{protocol.MSG_SAVE_PROGRESS}{protocol.SEPARATOR}{book_title}{protocol.SEPARATOR}{chapter_index}"
            packet = protocol.build_rudp_packet(seq_num=0, ack_num=0, flags=protocol.RUDP_FLAG_DATA,
                                                    payload=payload)
            try:
                self.sock.sendto(packet, self.server_addr)
            except Exception:
                pass

    def get_progress(self, book_title: str) -> int:
        """ Ask the server for the user's saved progress on a book. """
        if self.type == "TCP":
            msg = f"{protocol.MSG_GET_PROGRESS}{protocol.SEPARATOR}{book_title}"
            protocol.send_message(self.sock, msg)
            response = protocol.recv_message(self.sock)
            parts = response.split(protocol.SEPARATOR)
            if parts[0] == protocol.MSG_PROGRESS and len(parts) >= 2:
                return int(parts[1])
            return -1
        else:
            payload = f"{protocol.MSG_GET_PROGRESS}{protocol.SEPARATOR}{book_title}"
            packet = protocol.build_rudp_packet(seq_num=0, ack_num=0, flags=protocol.RUDP_FLAG_DATA,
                                                    payload=payload)
            for _ in range(3):
                self.server_response_event.clear()
                self.sock.sendto(packet, self.server_addr)
                if self.server_response_event.wait(timeout=2.0):
                    parts = self.server_response_payload.split(protocol.SEPARATOR)
                    if parts[0] == protocol.MSG_PROGRESS and len(parts) >= 2:
                        return int(parts[1])
            return -1

    def stop_reading(self):
        """ Tell the server to stop the chapter-streaming loop. """
        # Prevent deadlock: DON'T try to stop a stream if we aren't streaming!
        if not getattr(self, 'streaming', False):
            return

        self.book_finished = True
        self.streaming = False
        self.stop_prefetch()

        if self.type == "TCP" and self.sock:
            try:
                protocol.send_message(self.sock, protocol.MSG_STOP_READING)
                # Set a temporary timeout so it doesn't freeze forever if the server is quiet
                self.sock.settimeout(2.0)
                for _ in range(50):
                    resp = protocol.recv_message(self.sock)
                    if not resp or resp.startswith(protocol.MSG_END_OF_BOOK):
                        break
                self.sock.settimeout(None)  # Restore normal blocking mode
            except Exception:
                if self.sock:
                    self.sock.settimeout(None)

        elif self.type == "RUDP" and self.sock:
            packet = protocol.build_rudp_packet(seq_num=0, ack_num=0, flags=protocol.RUDP_FLAG_DATA,
                                                payload=protocol.MSG_STOP_READING)
            try:
                self.sock.sendto(packet, self.server_addr)
            except Exception:
                pass

    def get_last_book(self) -> tuple[str, int] | None:
        """ Ask the server for the last book this user was reading. """
        if self.type == "TCP":
            protocol.send_message(self.sock, protocol.MSG_GET_LAST_BOOK)
            response = protocol.recv_message(self.sock)
            parts = response.split(protocol.SEPARATOR)
            if parts[0] == protocol.MSG_LAST_BOOK:
                if len(parts) >= 3 and parts[1] != "NONE":
                    return parts[1], int(parts[2])
            return None
        else:
            packet = protocol.build_rudp_packet(seq_num=0, ack_num=0, flags=protocol.RUDP_FLAG_DATA,
                                                payload=protocol.MSG_GET_LAST_BOOK)
            for _ in range(3):
                self.server_response_event.clear()
                self.sock.sendto(packet, self.server_addr)
                if self.server_response_event.wait(timeout=2.0):
                    parts = self.server_response_payload.split(protocol.SEPARATOR)
                    if parts[0] == protocol.MSG_LAST_BOOK:
                        # Return None immediately if we received NONE, don't keep waiting!
                        if len(parts) >= 3 and parts[1] != "NONE":
                            return parts[1], int(parts[2])
                        return None
            return None

    # ==================== BOOK LIST ====================
    def request_book_list(self) -> list[dict]:
        """ Request the list of available books from the server. """
        if self.type == "TCP":
            protocol.send_message(self.sock, protocol.MSG_REQUEST_BOOK_LIST)
            response = protocol.recv_message(self.sock)
            parts = response.split(protocol.SEPARATOR, 1)

            if parts[0] != protocol.MSG_BOOK_LIST:
                return []

            count = int(parts[1])
            books = []
            for _ in range(count):
                item = protocol.recv_message(self.sock)
                item_parts = item.split(protocol.SEPARATOR, 4)
                if item_parts[0] == protocol.MSG_BOOK_LIST_ITEM:
                    books.append({
                        "title": item_parts[1],
                        "author": item_parts[2],
                        "chapters": int(item_parts[3]),
                        "cover": item_parts[4] if len(item_parts) > 4 else ""
                    })
            return books
        else:
            packet = protocol.build_rudp_packet(seq_num=0, ack_num=0, flags=protocol.RUDP_FLAG_DATA,
                                                payload=protocol.MSG_REQUEST_BOOK_LIST)

            for attempt in range(3):
                self.book_list_buffer.clear()  # <--- Clear buffer INSIDE the retry loop!
                self.server_response_event.clear()
                self.sock.sendto(packet, self.server_addr)

                # slightly longer wait to allow all packets to arrive
                if self.server_response_event.wait(timeout=3.0):
                    parts = self.server_response_payload.split(protocol.SEPARATOR, 1)
                    if parts[0] == protocol.MSG_BOOK_LIST:
                        # get the number of books the server is about to send
                        expected_count = int(parts[1])

                        # wait dynamically for all books to arrive
                        timeout_counter = 0
                        while len(
                                self.book_list_buffer) < expected_count and timeout_counter < 40:  # max 4 seconds wait
                            import time
                            time.sleep(0.1)
                            timeout_counter += 1

                        books = []
                        for item in self.book_list_buffer:
                            item_parts = item.split(protocol.SEPARATOR, 4)
                            if item_parts[0] == protocol.MSG_BOOK_LIST_ITEM:
                                books.append({
                                    "title": item_parts[1],
                                    "author": item_parts[2],
                                    "chapters": int(item_parts[3]),
                                    "cover": item_parts[4] if len(item_parts) > 4 else ""
                                })
                        return books
            return []