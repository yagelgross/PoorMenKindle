import socket
import threading
import protocol
import util
from RUDPHandle import ChapterAssembler




class NetworkManager:
    """
    Manages the server connection and implements a sliding-window
    chapter prefetch strategy (default: 2 chapters ahead).
    """

    def __init__(self, host='', port=12347, prefetch_count=5, type: str = "TCP"):
        """ Initialize the network manager."""
        self.type = type # type of connection (TCP or RUDP)
        self.host = host # server IP address
        self.port = port # server port
        self.prefetch_count = prefetch_count # number of chapters to prefetch ahead of the user's current position

        if self.type == "TCP": # if TCP, initialize TCP type socket
            self.sock: socket.socket | None = None
        elif self.type == "RUDP": # if RUDP, initialize UDP type socket
            self.server_addr = (self.host, self.port) # the server address consists of the host and port
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM) # create a UDP socket
            self.assembler = ChapterAssembler() # create a ChapterAssembler instance

        self.total_chapters = 0 # initialize total_chapters to 0
        self.book_title = "" # initialize book_title to an empty string

        # --- Chapter Buffer ---
        # Stores received chapters: {chapter_index: chapter_text}
        self.chapter_buffer: dict[int, str] = {} # a dictionary to store chapters
        self.next_server_index = 0 # the index of the next chapter to be fetched from the server
        self.current_read_index = 0 # the index of the current chapter the user is reading
        self.book_finished = False # a boolean indicating whether the book has been fully read or not

        # --- Threading primitives ---
        self._lock = threading.Lock() # lock for thread-safe access to the buffer
        self._chapter_ready = threading.Event() # event to signal that a chapter is ready for reading
        self._prefetch_thread: threading.Thread | None = None # thread for prefetching chapters
        self._running = False # flag to control the running state of the prefetch thread

        # --- Callback for UI updates ---
        self.on_chapter_ready = None  # set by ReadPage

        # --- Synchronization for RUDP ---
        self.server_response_payload = ""
        self.server_response_event = threading.Event() # is set when the server responds to a request
        self.book_list_buffer = [] # buffer for book list items
        self.streaming = False # flag to indicate if the user is currently reading a book

    def TCP_connect(self) -> bool:
        """ Establish a stable and persistent TCP connection to the server."""
        #Establish a persistent connection to the server.
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM) # open a TCP socket
            self.sock.connect((self.host, self.port)) # connect to the server
            return True
        except Exception as e:
            # Handle connection errors gracefully
            print(f"Connection failed: {e}")
            return False

    def RUDP_connect(self) -> bool:
        """ Connect to the server using RUDP."""
        self._running = True # signal the self we are up and running
        threading.Thread(target=self._rudp_listen_loop, daemon=True).start() # start the listen loop in a background thread
        return True

    def TCP_login(self, username: str, password: str) -> str:
        # Send login credentials. Returns 'SUCCESS' or 'FAIL'.
        packet = (f"{protocol.MSG_LOGIN}{protocol.SEPARATOR}" 
                  f"{util.Caesar_cipher(username, 7)}{protocol.SEPARATOR}"
                  f"{util.Caesar_cipher(password, 7)}") # Caesar ciphers the username and password and packs them together
        protocol.send_message(self.sock, packet) # send the packet to the server for authentication
        response = protocol.recv_message(self.sock) # receive the response from the server
        return util.Caesar_decipher(response, 4) # decipher the response using Caesar cipher

    def RUDP_login(self, username: str, password: str) -> str:
        """ Creates and sends a RUDP login packet securely using the listen loop. """
        # preparing the payload for the RUDP packet
        payload = (f"{protocol.MSG_LOGIN}{protocol.SEPARATOR}"
                   f"{util.Caesar_cipher(username, 7)}{protocol.SEPARATOR}"
                   f"{util.Caesar_cipher(password, 7)}")
        # packing the RUDP packet (header + payload)
        packet = protocol.build_rudp_packet(seq_num=0, ack_num=0, flags=protocol.RUDP_FLAG_DATA, payload=payload)

        # define reliability parameters
        max_retries = 5

        for attempt in range(max_retries):
            self.server_response_event.clear()  # reset the event before sending

            # transmit the packet
            self.sock.sendto(packet, self.server_addr)

            # wait for the main loop to catch the response and set the event
            if self.server_response_event.wait(timeout=2.0):
                # decipher the response
                return util.Caesar_decipher(self.server_response_payload, 4)

            print(f"Login attempt {attempt + 1} timed out. Retrying...") # debug print line

        # if we reach here, it means we've tried and failed
        return "FAIL"

    def TCP_request_book(self, book_title: str) -> bool:
        """ Request a book from the server using TCP."""
        #Request a book from the server.
        #Receives metadata, then starts the prefetch thread.
        # Reset state
        self.chapter_buffer.clear() # clear the buffer
        self.next_server_index = 0 # reset the index
        self.current_read_index = 0 # reset the current read index
        self.book_finished = False # reset the book finished flag
        self.book_title = book_title # set the book title

        # Send request
        msg = f"{protocol.MSG_REQUEST_BOOK}{protocol.SEPARATOR}{book_title}" # create the packet of the request
        protocol.send_message(self.sock, msg) # send the packet

        # Receive metadata
        response = protocol.recv_message(self.sock) # receive the response
        parts = response.split(protocol.SEPARATOR) # split the response into parts

        if parts[0] == protocol.MSG_BOOK_META:
            # Extract metadata
            self.total_chapters = int(parts[2]) # extract the total chapters
            print(f"Book '{book_title}' has {self.total_chapters} chapters.") # debug print line

            # Start background prefetch
            self.streaming = True # we have begun reading a book
            self._running = True # the thread is running
            self._prefetch_thread = threading.Thread(target=self._TCP_prefetch_loop, daemon=True) # define the TCP prefetch thread
            self._prefetch_thread.start() # start the prefetch thread
            return True
        else:
            print(f"Error: {response}") # debug print line
            return False

    def RUDP_request_book(self, book_title: str) -> bool:
        """ Request a book from the server using RUDP and start the prefetch loop. """
        self.chapter_buffer.clear() # clear the buffer
        self.next_server_index = 0 # reset the index
        self.current_read_index = 0 # reset the current read index
        self.book_finished = False # reset the book finished flag
        self.book_title = book_title # set the book title

        # preparing the RUDP packet
        payload = f"{protocol.MSG_REQUEST_BOOK}{protocol.SEPARATOR}{book_title}" # create the payload
        packet = protocol.build_rudp_packet(seq_num=0, ack_num=0, flags=protocol.RUDP_FLAG_DATA, payload=payload) # pack the packet

        # define reliability parameters
        max_retries = 5

        for attempt in range(max_retries):
            self.server_response_event.clear() # reset the event before sending
            self.sock.sendto(packet, self.server_addr) # send the packet

            # wait for the server's response via the listen loop
            if self.server_response_event.wait(timeout=2.0):
                parts = self.server_response_payload.split(protocol.SEPARATOR) # split the response into parts
                if parts[0] == protocol.MSG_BOOK_META: # check if the response is a book meta message
                    self.total_chapters = int(parts[2]) # extract the total chapters
                    print(f"Book '{book_title}' has {self.total_chapters} chapters.") # debug print line

                    # Start background prefetch
                    self.streaming = True # we have begun reading a book
                    self._running = True # the thread is running
                    self._prefetch_thread = threading.Thread(target=self._rudp_prefetch_loop, daemon=True) # define the RUDP prefetch thread
                    self._prefetch_thread.start() # start the prefetch thread
                    return True

            print(f"Request book attempt {attempt + 1} timed out. Retrying...") # debug print line

        return False

    def _rudp_listen_loop(self):
        """
        A background thread that continuously listens for incoming RUDP packets from the server,
        processes them, assembles chapters, and wakes up waiting functions.
        """
        # set a fixed timeout to prevent Errno 35 and allow graceful exit
        self.sock.settimeout(1.0)

        while self._running: # loop until the thread is stopped
            try:
                # receiving a UDP packet
                data, addr = self.sock.recvfrom(65536) # receive a UDP packet, up to 64KB due to the book covers size
            except (socket.timeout, BlockingIOError): # if the timeout is reached or the socket is closed
                continue  # normal behavior, keep listening
            except Exception as e: # if there's an error, log it and continue
                if self._running:
                    print(f"UDP Listen Loop Error: {e}") # debug print line
                continue

            try:
                # unpacking the RUDP packet using the protocol class
                seq_num, ack_num, flags, payload = protocol.parse_rudp_packet(data)

                # if it is a data packet, send an ACK
                if flags & protocol.RUDP_FLAG_DATA:
                    ack_packet = protocol.build_rudp_packet(seq_num=0, ack_num=seq_num, flags=protocol.RUDP_FLAG_ACK,
                                                            payload="") # build an ACK packet
                    self.sock.sendto(ack_packet, self.server_addr) # send the ACK packet

                    # assemble the chapter from the received chunks
                    if payload.startswith("CHUNK|"): # check if the payload starts with "CHUNK|"
                        result = self.assembler.receive_chunk(payload) # call the assembler to assemble the chapter

                        # unpack the tuple!
                        if result:
                            chap_idx, assembled_text = result # unpack the result tuple
                            with self._lock:
                                self.chapter_buffer[chap_idx] = assembled_text # store the assembled chapter in the buffer
                                self.next_server_index = chap_idx + 1 # update the next server index
                                print(f"[RUDP] Successfully assembled chapter {chap_idx}") # debug print line

                            # update the UI with the new chapter
                            self._chapter_ready.set() # notify the UI that a chapter is ready
                            if self.on_chapter_ready: # check if the user has provided a callback
                                self.on_chapter_ready(chap_idx) # call the callback to notify the user
                    else:
                    # catch book list items separately
                        if payload.startswith(protocol.MSG_BOOK_LIST_ITEM): # check if the payload starts with the book list item prefix
                            self.book_list_buffer.append(payload) # add the item to the buffer
                        else:
                            # if it's not a chunk or a list item, it's LOGIN SUCCESS, BOOK_META, or BOOK_LIST header
                            self.server_response_payload = payload # store the payload for later processing
                            self.server_response_event.set() # set the event to indicate that the response is ready

                            if payload == protocol.MSG_END_OF_BOOK: # if we received the end-of-book message, stop the loop
                                self.book_finished = True # set the book finished flag
                                break

            except Exception as e: # if there's an error, log it and continue
                print(f"Packet processing error: {e}")

    def _TCP_prefetch_loop(self):
        """
        Background thread: keeps the buffer filled to `prefetch_count`
        chapters ahead of what the user is currently reading.
        """
        while self._running and not self.book_finished: # as long as there any chapters left to fetch
            with self._lock:
                buffered_ahead = self.next_server_index - self.current_read_index # how many chapters ahead are we?
                need_more = buffered_ahead < self.prefetch_count # do we need more?
                all_requested = self.next_server_index >= self.total_chapters # have we reached the end?

            if all_requested:
                # We've requested everything, wait for the user to finish
                threading.Event().wait(timeout=0.1)
                continue

            if need_more:
                # Request next chapter from server
                protocol.send_message(self.sock, protocol.MSG_NEXT_CHAPTER) # send the request
                response = protocol.recv_message(self.sock) # receive the response
                if not response:
                    self.book_finished = True # set the book finished flag
                    break # exit the loop if no response

                parts = response.split(protocol.SEPARATOR, 2)  # max split = 2 (chapter text may contain |)

                if parts[0] == protocol.MSG_CHAPTER: # check if the response is a chapter message
                    chapter_idx = int(parts[1]) # extract the chapter index
                    chapter_text = parts[2] # extract the chapter text

                    with self._lock:
                        self.chapter_buffer[chapter_idx] = chapter_text # store the chapter in the buffer
                        self.next_server_index = chapter_idx + 1 # update the next server index
                        print(f"  [Prefetch] Buffered chapter {chapter_idx} " 
                              f"(buffer: {self.next_server_index - self.current_read_index} ahead)") # debug print line
                    # Notify UI that a chapter is ready
                    self._chapter_ready.set()
                    if self.on_chapter_ready:
                        self.on_chapter_ready(chapter_idx)

                elif parts[0] == protocol.MSG_END_OF_BOOK: # check if the response is the end-of-book message
                    self.book_finished = True # set the book finished flag
                    break # exit the loop if we reached the end of the book
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
                buffered_ahead = self.next_server_index - self.current_read_index # how many chapters ahead are we?
                need_more = buffered_ahead < self.prefetch_count # do we need more?
                all_requested = self.next_server_index >= self.total_chapters # have we reached the end?

            if all_requested:
                threading.Event().wait(timeout=0.1) # wait for the user to finish
                continue

            if need_more: # if we need more,
                # request the specific next chapter from the server
                payload = f"{protocol.MSG_NEXT_CHAPTER}{protocol.SEPARATOR}{self.next_server_index}"
                packet = protocol.build_rudp_packet(seq_num=0, ack_num=0, flags=protocol.RUDP_FLAG_DATA,
                                                    payload=payload)
                self.sock.sendto(packet, self.server_addr) # create the packet and send it

                # save the current index for comparison
                expected_index = self.next_server_index

                # wait for the server to send the next chapter.
                # increased timeout to prevent spamming the server if UDP is slow
                timeout_counter = 0
                max_wait_cycles = 50  # max 5 seconds of waiting

                while self._running and self.next_server_index == expected_index and timeout_counter < max_wait_cycles:
                    # as long as the server hasn't sent the next chapter, wait a bit
                    threading.Event().wait(timeout=0.1)
                    timeout_counter += 1 # increment the timeout counter

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
            return self.chapter_buffer.get(index, None) # return the chapter if it's in the buffer, None otherwise

    def notify_user_advanced(self, new_read_index: int):
        """
        Called when the user moves to a new chapter.
        Updates current_read_index so the prefetch thread knows it can fetch more.
        """
        with self._lock:
            self.current_read_index = new_read_index # update the current read index

            # Optionally: evict old chapters to save memory
            #keys_to_remove = [k for k in self.chapter_buffer if k < new_read_index - 1]
            #for k in keys_to_remove:
                #del self.chapter_buffer[k]

    def stop(self):
        #Stop prefetching and close the connection.
        self._running = False
        if self.sock:
            # noinspection PyBroadException
            try:
                self.sock.close()

            except Exception:
                pass

    def connect(self) -> bool:
        """Establish a connection to the server using the desired protocol."""
        if self.type == "TCP":
            return self.TCP_connect()
        else:
            return self.RUDP_connect()

    def login(self, username: str, password: str) -> str:
        """Login to the server using the desired protocol."""
        if self.type == "TCP":
            return self.TCP_login(username, password)
        else:
            return self.RUDP_login(username, password)

    def request_book(self, book_title: str) -> bool:
        """Request a book from the server using the desired protocol."""
        if self.type == "TCP":
            return self.TCP_request_book(book_title)
        else:
            return self.RUDP_request_book(book_title)

    # ==================== READING PROGRESS & CONTROL ====================

    def stop_prefetch(self):
        """ stop the prefetch thread without killing the rudp listen loop """
        # we use the book_finished flag to stop the prefetch loop instead of _running
        self.book_finished = True

        if self._prefetch_thread:
            self._prefetch_thread.join(timeout=1.0)
            self._prefetch_thread = None

    # noinspection PyBroadException
    def save_progress(self, book_title: str, chapter_index: int):
        """ Tell the server to save reading progress for the current user. (Fire and forget) """
        if self.type == "TCP": # if the protocol is TCP, send a TCP message
            msg = f"{protocol.MSG_SAVE_PROGRESS}{protocol.SEPARATOR}{book_title}{protocol.SEPARATOR}{chapter_index}"
            try:
                protocol.send_message(self.sock, msg)
            except Exception:
                pass
        else: # if the protocol is RUDP, send a RUDP packet
            payload = f"{protocol.MSG_SAVE_PROGRESS}{protocol.SEPARATOR}{book_title}{protocol.SEPARATOR}{chapter_index}"
            packet = protocol.build_rudp_packet(seq_num=0, ack_num=0, flags=protocol.RUDP_FLAG_DATA,
                                                    payload=payload)
            try:
                self.sock.sendto(packet, self.server_addr)
            except Exception:
                pass

    def get_progress(self, book_title: str) -> int:
        """Ask the server for the user's saved progress on a book. (Fire and forget)"""
        if self.type == "TCP": # if the protocol is TCP, send a TCP message
            msg = f"{protocol.MSG_GET_PROGRESS}{protocol.SEPARATOR}{book_title}"
            protocol.send_message(self.sock, msg)
            response = protocol.recv_message(self.sock) # parse the response and extract the chapter index
            parts = response.split(protocol.SEPARATOR)
            if parts[0] == protocol.MSG_PROGRESS and len(parts) >= 2:
                return int(parts[1])
            return -1 # return -1 if we didn't get a valid response
        else: # if the protocol is RUDP, send a RUDP packet
            payload = f"{protocol.MSG_GET_PROGRESS}{protocol.SEPARATOR}{book_title}"
            packet = protocol.build_rudp_packet(seq_num=0, ack_num=0, flags=protocol.RUDP_FLAG_DATA,
                                                    payload=payload)
            for _ in range(3): # retry 3 times for reliability assurance
                self.server_response_event.clear() # reset the event before sending
                self.sock.sendto(packet, self.server_addr) # send the packet
                if self.server_response_event.wait(timeout=2.0): # wait for the response
                    parts = self.server_response_payload.split(protocol.SEPARATOR) # parse the response
                    if parts[0] == protocol.MSG_PROGRESS and len(parts) >= 2:
                        return int(parts[1])
            return -1 # return -1 if we didn't get a valid response after 3 retries

    # noinspection PyBroadException
    def stop_reading(self):
        """ Tell the server to stop the chapter-streaming loop. """
        # Prevent deadlock: DON'T try to stop a stream if we aren't streaming!
        if not getattr(self, 'streaming', False): # if we aren't streaming, return immediately'
            return

        self.book_finished = True # set the book finished flag to stop the prefetch loop
        self.streaming = False # set the streaming flag to false
        self.stop_prefetch() # stop the prefetch thread

        if self.type == "TCP" and self.sock: # if the protocol is TCP, send a TCP message
            try:
                protocol.send_message(self.sock, protocol.MSG_STOP_READING) # send the stop message
                # Set a temporary timeout so it doesn't freeze forever if the server is quiet
                self.sock.settimeout(2.0)
                for _ in range(50): # wait for the server to acknowledge the stop message
                    resp = protocol.recv_message(self.sock) # receive the response
                    if not resp or resp.startswith(protocol.MSG_END_OF_BOOK): # if the response is empty or the end-of-book message, stop waiting
                        break # exit the loop
                self.sock.settimeout(None)  # Restore normal blocking mode
            except Exception: # if there's an error, ignore it and continue
                if self.sock:
                    self.sock.settimeout(None)

        elif self.type == "RUDP" and self.sock: # if the protocol is RUDP, send a RUDP packet
            packet = protocol.build_rudp_packet(seq_num=0, ack_num=0, flags=protocol.RUDP_FLAG_DATA,
                                                payload=protocol.MSG_STOP_READING)
            try:
                self.sock.sendto(packet, self.server_addr)
            except Exception:
                pass

    def get_last_book(self) -> tuple[str, int] | None:
        """ Ask the server for the last book this user was reading. Returns (book_title, chapter_index) or None if no record. """
        if self.type == "TCP": # if the protocol is TCP, send a TCP message
            protocol.send_message(self.sock, protocol.MSG_GET_LAST_BOOK) # send the message
            response = protocol.recv_message(self.sock) # receive the response
            parts = response.split(protocol.SEPARATOR) # split the response into parts and extract the data
            if parts[0] == protocol.MSG_LAST_BOOK:
                if len(parts) >= 3 and parts[1] != "NONE":
                    return parts[1], int(parts[2])
            return None
        else: # if the protocol is RUDP, send a RUDP packet
            packet = protocol.build_rudp_packet(seq_num=0, ack_num=0, flags=protocol.RUDP_FLAG_DATA,
                                                payload=protocol.MSG_GET_LAST_BOOK)
            for _ in range(5): # retry 5 times for reliability
                self.server_response_event.clear() # reset the event before sending
                self.sock.sendto(packet, self.server_addr) # send the packet
                if self.server_response_event.wait(timeout=2.0): # if we received a response, parse it and return the data
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
        if self.type == "TCP": # if the protocol is TCP, send a TCP message
            protocol.send_message(self.sock, protocol.MSG_REQUEST_BOOK_LIST)
            response = protocol.recv_message(self.sock) # receive the response
            parts = response.split(protocol.SEPARATOR, 1) # split the response into parts and extract the data

            if parts[0] != protocol.MSG_BOOK_LIST: # if we got the wrong message type, return an empty list
                return []

            count = int(parts[1]) # extract the number of books from the second part
            books = []
            for _ in range(count): # iterate over the number of books
                item = protocol.recv_message(self.sock)
                item_parts = item.split(protocol.SEPARATOR, 4) # split the item into parts and extract the data
                if item_parts[0] == protocol.MSG_BOOK_LIST_ITEM: # if the item is a book, add it to the list
                    books.append({
                        "title": item_parts[1],
                        "author": item_parts[2],
                        "chapters": int(item_parts[3]),
                        "cover": item_parts[4] if len(item_parts) > 4 else ""
                    }) # adding the book object to the list
            return books
        else: # if the protocol is RUDP, send a RUDP packet
            packet = protocol.build_rudp_packet(seq_num=0, ack_num=0, flags=protocol.RUDP_FLAG_DATA,
                                                payload=protocol.MSG_REQUEST_BOOK_LIST)

            for attempt in range(5): # retry 5 times for reliability
                self.book_list_buffer.clear()  # clear the buffer for every iteration of the reliability loop
                self.server_response_event.clear() # reset the event before sending
                self.sock.sendto(packet, self.server_addr) # send the packet

                # slightly longer wait to allow all packets to arrive
                if self.server_response_event.wait(timeout=3.0): # if we received a response, parse it and return the data
                    parts = self.server_response_payload.split(protocol.SEPARATOR, 1) # split the response into parts and extract the data
                    if parts[0] == protocol.MSG_BOOK_LIST: # assuming the response is a book list, check the type
                        # get the number of books the server is about to send
                        expected_count = int(parts[1])

                        # wait dynamically for all books to arrive
                        timeout_counter = 0
                        while len(self.book_list_buffer) < expected_count and timeout_counter < 40:  # max 4-second wait
                            import time
                            time.sleep(0.1) # wait a bit before checking again
                            timeout_counter += 1 # increment the timeout counter for the reliability loop

                        books = [] # create an empty book list
                        for item in self.book_list_buffer:
                            item_parts = item.split(protocol.SEPARATOR, 4) # split the item into parts and extract the data
                            if item_parts[0] == protocol.MSG_BOOK_LIST_ITEM: # if the item is a book, add it to the list
                                books.append({
                                    "title": item_parts[1],
                                    "author": item_parts[2],
                                    "chapters": int(item_parts[3]),
                                    "cover": item_parts[4] if len(item_parts) > 4 else ""
                                }) # adding the book object to the list
                        return books
            return [] # return an empty list if we didn't get a valid response after 5 attempts'