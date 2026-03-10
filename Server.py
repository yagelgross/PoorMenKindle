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

# --- Server side important Data---
currClients: list[Client.Client] = [] # a list of all currently connected clients

availableBooks = [
    Book.Book("Eragon",      "Christopher Paolini", 50, "booksForServer/Eragon.epub",      "booksForServer/covers/Eragon.jpg"),
    Book.Book("Eldest",      "Christopher Paolini", 83, "booksForServer/Eldest.epub",       "booksForServer/covers/Eldest.png"),
    Book.Book("Brisingr",    "Christopher Paolini", 68, "booksForServer/Brisingr.epub",     "booksForServer/covers/Brisingr.png"),
    Book.Book("Inheritance", "Christopher Paolini", 88, "booksForServer/Inheritance.epub",  "booksForServer/covers/Inheritance.jpg"),
    Book.Book("אראגון", "כריסטופר פאוליני", 64, "booksForServer/אראגון.epub",      "booksForServer/covers/אראגון.jpeg"),
] # a list of all the books available on the server. In a real application, this would likely be loaded from a database or filesystem scan rather than hardcoded.

AllClients = [
    Client.Client("yagel", "123456", True),
    Client.Client("noam", "123456", True),
    Client.Client("taltul", "123456", False),
] # a list of all the clients authorized to connect to the server. In a real application, this would likely be loaded from a database or filesystem scan rather than hardcoded.

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
    if addr not in udp_client_seq: # if this is the first time we've seen this client, initialize the sequence number to 0
        udp_client_seq[addr] = 0
    seq = udp_client_seq[addr] # get the current sequence number
    udp_client_seq[addr] += 1 # increment the sequence number
    return seq


def send_rudp_reliable(server_socket: socket.socket, addr: tuple, payload: str):
    """
    Pack the payload into a RUDP packet and send it to the client. Then, add it to the unacked messages list.
    """
    seq_num = get_next_seq(addr) # get the next sequence number for this client
    packet = protocol.build_rudp_packet(seq_num=seq_num, ack_num=0, flags=protocol.RUDP_FLAG_DATA, payload=payload)

    server_socket.sendto(packet, addr) # send the packet to the client

    # save to unacked messages if needed (for simplicity, we assume all messages require ACKs in this implementation)
    udp_unacked_messages[(addr, seq_num)] = {
        'packet': packet,
        'timestamp': time.time(),
        'retries': 0
    } # for simplicity, we assume all messages require ACKs in this implementation


def udp_retransmission_loop(server_socket: socket.socket):
    """
    Server side background thread that handles retransmissions of unacknowledged messages.
    """
    timeout_limit = 0.5  # half a second
    max_retries = 5 # max number of retransmissions for reliability before giving up on the client and dropping the packet

    while True: # as long as we need to keep running the thread, keep looping
        current_time = time.time() # get the current time
        # use a local list so that we do not modify the dict while iterating
        for key, info in list(udp_unacked_messages.items()): # iterate over the unacked messages
            addr, seq_num = key

            if current_time - info['timestamp'] > timeout_limit: # if the packet has timed out
                if info['retries'] < max_retries: # and if we haven't reached the max number of retries, retransmit the packet
                    info['timestamp'] = current_time # update the timestamp
                    info['retries'] += 1 # increment the retry count
                    server_socket.sendto(info['packet'], addr) # retransmit the packet
                    print(f"[RUDP Server] Retransmitting seq {seq_num} to {addr}") # debug print line
                else:
                    print(f"[RUDP Server] Client {addr} unresponsive. Dropping packet {seq_num}") # debug print line
                    del udp_unacked_messages[key] # remove the packet from the unacked messages list since the client is unresponsive

        time.sleep(0.05) # wait for a short period before checking again


def process_udp_request(server_socket: socket.socket, addr: tuple, payload: str):
    """
    The business side of the server. Handles login, book requests, book lists, and progress over RUDP.
    """
    parts = payload.split(protocol.SEPARATOR) # parse the payload into parts
    msg_type = parts[0] # extract the message type

    # --- LOGIN ---
    if msg_type == protocol.MSG_LOGIN and len(parts) == 3: # if this is a login request, decrypt the username and password and check if it's valid
        username = util.Caesar_decipher(parts[1], 7)
        password = util.Caesar_decipher(parts[2], 7)

        if validate_user(username, password): # if the username and password are valid, authenticate the client
            send_rudp_reliable(server_socket, addr, util.Caesar_cipher("SUCCESS", 4))
            udp_client_state[addr] = {'username': username, 'authenticated': True}
            print(f"[RUDP Server] User '{username}' authenticated from {addr}.")
        else: # update the client that it has failed to authenticate
            send_rudp_reliable(server_socket, addr, util.Caesar_cipher("FAIL", 4))
        return  # return here so it doesn't execute the rest of the function on login

    # block all other requests from unauthenticated clients
    if addr not in udp_client_state or not udp_client_state[addr].get('authenticated'):
        return

    state = udp_client_state[addr] # get the client's state
    username = state['username'] # get the client's username

    # --- BOOK LIST ---
    if msg_type == protocol.MSG_REQUEST_BOOK_LIST: # if the client is requesting a book list, send the book list
        # send header: BOOK_LIST|count
        send_rudp_reliable(server_socket, addr, f"{protocol.MSG_BOOK_LIST}{protocol.SEPARATOR}{len(availableBooks)}") # send the number of available books
        # send one BOOK_LIST_ITEM per book
        for book in availableBooks: # iterate over all available books
            cover_b64 = get_cover_base64(book) # get the cover image as a base64 string
            item = (f"{protocol.MSG_BOOK_LIST_ITEM}"
                    f"{protocol.SEPARATOR}{book.title}"
                    f"{protocol.SEPARATOR}{book.author}"
                    f"{protocol.SEPARATOR}{book.chapterCount}"
                    f"{protocol.SEPARATOR}{cover_b64}") # build the book list item message
            send_rudp_reliable(server_socket, addr, item) # send the book list item to the client
        print(f"[RUDP Server] Sent book list ({len(availableBooks)} books) to {addr}") # debug print line

    # --- REQUEST BOOK ---
    elif msg_type == protocol.MSG_REQUEST_BOOK and len(parts) == 2: # if the client is requesting a specific book
        book_title = parts[1] # extract the book title from the request
        chapters = epub_handler(book_title) # parse the EPUB file and get the list of chapter texts

        if chapters is None: # if the book was not found or failed to parse
            send_rudp_reliable(server_socket, addr, f"{protocol.MSG_ERROR}|Book not found") # send an error message to the client
            return

        # state metadata: what book the client is currently reading and what chapter it is on
        state['current_book'] = book_title # store the book title in the client's state
        state['chapter_index'] = 0 # start from the first chapter

        meta = f"{protocol.MSG_BOOK_META}{protocol.SEPARATOR}{book_title}{protocol.SEPARATOR}{len(chapters)}" # build the metadata message
        send_rudp_reliable(server_socket, addr, meta) # send the metadata to the client

    # --- NEXT CHAPTER ---
    elif msg_type == protocol.MSG_NEXT_CHAPTER: # if the client is requesting the next chapter
        book_title = state.get('current_book') # get the book the client is currently reading

        # extract the specific index requested by the client (if provided)
        if len(parts) > 1: # if the client specified a chapter index
            req_index = int(parts[1]) # use the requested index
        else:
            req_index = state.get('chapter_index', 0) # otherwise, use the server's tracked index

        if not book_title: # if the client hasn't requested a book yet, ignore the request
            return

        # anti-spam mechanism: if we just sent this chapter, don't re-chunk and re-send it all at once.
        last_sent = state.get('last_sent_chapter', -1) # get the last chapter we sent to this client
        if last_sent == req_index: # if we already sent this chapter, ignore the request
            return

        chapters = epub_handler(book_title) # parse the EPUB file and get the list of chapter texts

        if chapters and req_index < len(chapters): # if the requested chapter exists
            chapter_text = chapters[req_index] # get the text of the requested chapter

            # chunk up the chapter text into smaller packets for RUDP transmission
            most_chars = 500 # maximum number of characters per chunk
            total_chunks = (len(chapter_text) + most_chars - 1) // most_chars # calculate the number of chunks needed (ceiling division)

            for i in range(total_chunks): # send each chunk as a separate RUDP packet
                start = i * most_chars # start index of the chunk
                end = start + most_chars # end index of the chunk
                chunk_payload = f"CHUNK|{book_title}|{req_index}|{total_chunks}|{i}|{chapter_text[start:end]}" # build the chunk payload
                send_rudp_reliable(server_socket, addr, chunk_payload) # send the chunk to the client

            print(f"[RUDP Server] Sent chapter {req_index} ({total_chunks} chunks) to {addr}") # debug print line

            state['chapter_index'] = req_index + 1 # advance the server's tracked chapter index
            state['last_sent_chapter'] = req_index # remember the last chapter we sent (for anti-spam)

        elif chapters and req_index >= len(chapters): # if the client requested a chapter beyond the end of the book
            send_rudp_reliable(server_socket, addr, protocol.MSG_END_OF_BOOK) # notify the client that the book is finished

    # --- SAVE PROGRESS ---
    elif msg_type == protocol.MSG_SAVE_PROGRESS and len(parts) == 3: # if the client is saving reading progress
        book_title = parts[1] # extract the book title
        chapter = int(parts[2]) # extract the chapter index

        # find the client object by username
        client_obj = next((c for c in AllClients if c.getUserName() == username), None) # search for the client in the AllClients list
        if client_obj: # if the client was found
            client_obj.setCurrChapter(book_title, chapter) # save the reading progress
            print(f"[RUDP Server] Saved progress: {username} -> {book_title} ch.{chapter}") # debug print line

    # --- GET PROGRESS ---
    elif msg_type == protocol.MSG_GET_PROGRESS and len(parts) == 2: # if the client is requesting their saved progress for a book
        book_title = parts[1] # extract the book title
        client_obj = next((c for c in AllClients if c.getUserName() == username), None) # search for the client in the AllClients list
        chapter = -1 # default to -1 (no progress saved)
        if client_obj: # if the client was found
            chapter = client_obj.getCurrChapter(book_title) # get the saved chapter index
        send_rudp_reliable(server_socket, addr, f"{protocol.MSG_PROGRESS}{protocol.SEPARATOR}{chapter}") # send the progress back to the client

    # --- GET LAST BOOK ---
    elif msg_type == protocol.MSG_GET_LAST_BOOK: # if the client is requesting the last book they were reading
        client_obj = next((c for c in AllClients if c.getUserName() == username), None) # search for the client in the AllClients list
        if client_obj and client_obj.lastBookRead: # if the client was found and has a last book
            title = client_obj.lastBookRead # get the title of the last book
            chapter = client_obj.getCurrChapter(title) # get the chapter index of the last book
            send_rudp_reliable(server_socket, addr,
                               f"{protocol.MSG_LAST_BOOK}{protocol.SEPARATOR}{title}{protocol.SEPARATOR}{chapter}") # send the last book info to the client
        else: # if the client has no last book
            send_rudp_reliable(server_socket, addr, f"{protocol.MSG_LAST_BOOK}{protocol.SEPARATOR}NONE") # send NONE to the client


def start_UDP_server():
    """Activates the RUDP server and starts listening for incoming connections."""
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM) # open a UDP socket
    server_socket.bind(('', 12347)) # bind the socket to port 12347
    print("RUDP Server listening on port 12347...") # debug print line

    # start the retransmission background thread to handle unacknowledged messages
    threading.Thread(target=udp_retransmission_loop, args=(server_socket,), daemon=True).start()

    while True: # main RUDP server loop
        try:
            data, addr = server_socket.recvfrom(4096) # receive a UDP packet from a client
            seq_num, ack_num, flags, payload = protocol.parse_rudp_packet(data) # unpack the RUDP packet header and payload

            # if the packet is an ACK, update the unacked messages list
            if flags & protocol.RUDP_FLAG_ACK: # check if the ACK flag is set
                key = (addr, ack_num) # build the key to look up the unacked message
                if key in udp_unacked_messages: # if we have an unacked message for this ACK
                    del udp_unacked_messages[key]  # delete the acknowledged packet from the unacked messages
                    print(f"[RUDP Server] Received ACK for seq {ack_num} from {addr}") # debug print line
                else:
                    print(f"[RUDP Server] Received ACK for seq {ack_num} from {addr}, but no corresponding packet was unacked.") # debug print line

            # if the packet is a DATA packet, process it
            if flags & protocol.RUDP_FLAG_DATA: # check if the DATA flag is set
                # first, send an ACK back to the client to confirm receipt
                ack_packet = protocol.build_rudp_packet(seq_num=0, ack_num=seq_num, flags=protocol.RUDP_FLAG_ACK,
                                                        payload="") # build an ACK packet with the received sequence number
                server_socket.sendto(ack_packet, addr) # send the ACK packet to the client

                # now we can handle the client's request in a background thread
                # since we've already acknowledged receipt, retransmissions from the client won't cause issues
                threading.Thread(target=process_udp_request, args=(server_socket, addr, payload), daemon=True).start()

        except Exception as e:
            print(f"RUDP Server Error: {e}") # debug print line

# TCP server logistics and functions
def get_cover_base64(book: Book.Book) -> str:
    """A method to read a book's cover image, resize it to a lightweight thumbnail, and return it as a base64 string."""
    if book.coverPath and os.path.exists(book.coverPath): # check if the book has a cover path and the file exists
        try:
            with Image.open(book.coverPath) as img: # open the cover image
                img.thumbnail((100, 130)) # resize to a small thumbnail to save bandwidth

                # convert to RGB (removes alpha channel if it's a PNG) to allow JPEG compression
                if img.mode != 'RGB':
                    img = img.convert('RGB')

                buffer = io.BytesIO() # create an in-memory byte buffer
                img.save(buffer, format="JPEG", quality=70) # compress heavily into JPEG format

                return base64.b64encode(buffer.getvalue()).decode("ascii") # encode the image bytes as a base64 ASCII string
        except Exception as e:
            print(f"Error processing cover for {book.title}: {e}") # debug print line
    return "" # return an empty string if no cover is available


def epub_handler(bookname: str) -> list[str] | None:
    """A method to parse an EPUB file and return a list of chapter texts. Uses a cache to avoid reparsing."""
    if bookname in book_cache: # if the book has already been parsed, return the cached result
        return book_cache[bookname]

    try:
        path = f"booksForServer/{bookname}.epub" # build the file path based on the book name
        book = epub.read_epub(path) # parse the EPUB file using ebooklib
        chapters = [] # list to store the extracted chapter texts
        for item in book.get_items(): # iterate over all items in the EPUB
            if item.get_type() == ebooklib.ITEM_DOCUMENT: # only process document items (chapters)
                soup = BeautifulSoup(item.get_content(), 'html.parser') # parse the HTML content using BeautifulSoup
                # noinspection PyArgumentList
                text = soup.get_text(separator='\n\n', strip=True) # extract plain text with double newlines between paragraphs
                if text: # only add non-empty chapters
                    chapters.append(text)
        book_cache[bookname] = chapters # cache the parsed chapters for future requests
        return chapters
    except Exception as e:
        print(f"Error loading book '{bookname}': {e}") # debug print line
        return None


def validate_user(username: str, password: str) -> bool:
    """A method to validate a username and password against the AllClients list."""
    for client in AllClients: # iterate over all authorized clients
        if client.getUserName() == username and client.getPassword() == password: # if the credentials match
            if client not in currClients: # if the client is not already in the connected clients list
                currClients.append(client) # add the client to the connected clients list
            return True # return True to indicate successful authentication
    return False # return False if no matching client was found


def handle_TCP_client(conn: socket.socket, addr):
    """Handle one client connection through login → book request → chapter streaming."""
    print(f"Client connected from: {addr}") # debug print line
    authenticated = False # flag to track whether the client has successfully logged in

    try:
        while True: # the main TCP client loop — keep processing messages until the client disconnects
            raw = protocol.recv_message(conn) # receive the next length-prefixed message from the client
            if not raw: # if the message is empty, the client has disconnected
                print(f"Client {addr} disconnected.") # debug print line
                break

            parts = raw.split(protocol.SEPARATOR) # parse the message into parts
            msg_type = parts[0] # extract the message type

            # ─── LOGIN ───
            if msg_type == protocol.MSG_LOGIN and len(parts) == 3: # if this is a login request
                username = util.Caesar_decipher(parts[1], 7) # decrypt the username using Caesar cipher
                password = util.Caesar_decipher(parts[2], 7) # decrypt the password using Caesar cipher

                if validate_user(username, password): # if the credentials are valid
                    protocol.send_message(conn, util.Caesar_cipher("SUCCESS", 4)) # send an encrypted success response
                    authenticated = True # mark the client as authenticated
                    # Store reference to the authenticated Client object for progress tracking
                    for c in AllClients: # search for the matching Client object
                        if c.getUserName() == username:
                            current_client_map[addr] = c # map the client's address to their Client object
                            break
                    print(f"User '{username}' authenticated.") # debug print line
                else: # if the credentials are invalid
                    protocol.send_message(conn, util.Caesar_cipher("FAIL", 4)) # send an encrypted failure response

            # ─── BOOK LIST ───
            elif msg_type == protocol.MSG_REQUEST_BOOK_LIST and authenticated: # if the client is requesting the book list
                # send header: BOOK_LIST|count
                protocol.send_message(
                    conn,
                    f"{protocol.MSG_BOOK_LIST}{protocol.SEPARATOR}{len(availableBooks)}" # send the number of available books
                )
                # send one BOOK_LIST_ITEM per book
                for book in availableBooks: # iterate over all available books
                    cover_b64 = get_cover_base64(book) # get the cover image as a base64 string
                    item = (f"{protocol.MSG_BOOK_LIST_ITEM}"
                            f"{protocol.SEPARATOR}{book.title}"
                            f"{protocol.SEPARATOR}{book.author}"
                            f"{protocol.SEPARATOR}{book.chapterCount}"
                            f"{protocol.SEPARATOR}{cover_b64}") # build the book list item message
                    protocol.send_message(conn, item) # send the book list item to the client
                print(f"Sent book list ({len(availableBooks)} books) to {addr}") # debug print line

            # ─── REQUEST BOOK ───
            elif msg_type == protocol.MSG_REQUEST_BOOK and len(parts) == 2 and authenticated: # if the client is requesting a specific book
                book_title = parts[1] # extract the book title from the request
                chapters = epub_handler(book_title) # parse the EPUB file and get the list of chapter texts

                if chapters is None: # if the book was not found or failed to parse
                    protocol.send_message(conn, f"{protocol.MSG_ERROR}|Book not found") # send an error message
                    continue # skip to the next message

                # Send metadata: total number of chapters
                meta = f"{protocol.MSG_BOOK_META}{protocol.SEPARATOR}{book_title}{protocol.SEPARATOR}{len(chapters)}" # build the metadata message
                protocol.send_message(conn, meta) # send the metadata to the client

                # Chapter-streaming loop — send chapters one at a time as the client requests them
                chapter_index = 0 # start from the first chapter
                while chapter_index < len(chapters): # keep streaming until we've sent all chapters or the client stops
                    req = protocol.recv_message(conn) # wait for the client's next request
                    if not req: # if the client disconnected during streaming
                        print(f"Client {addr} disconnected during streaming.") # debug print line
                        return

                    if req == protocol.MSG_NEXT_CHAPTER: # if the client wants the next chapter
                        msg = (f"{protocol.MSG_CHAPTER}"
                               f"{protocol.SEPARATOR}{chapter_index}"
                               f"{protocol.SEPARATOR}{chapters[chapter_index]}") # build the chapter message
                        protocol.send_message(conn, msg) # send the chapter to the client
                        chapter_index += 1 # advance to the next chapter

                    elif req == protocol.MSG_PREV_CHAPTER: # if the client wants the previous chapter
                        if chapter_index > 0: # check if there is a previous chapter
                            chapter_index -= 1 # go back one chapter
                            msg = (f"{protocol.MSG_CHAPTER}"
                                   f"{protocol.SEPARATOR}{chapter_index}"
                                   f"{protocol.SEPARATOR}{chapters[chapter_index]}") # build the chapter message
                            protocol.send_message(conn, msg) # send the chapter to the client

                    elif req == protocol.MSG_STOP_READING: # if the client wants to stop reading
                        print(f"Client {addr} stopped reading '{book_title}' at ch.{chapter_index}") # debug print line
                        break # exit the streaming loop

                    elif req.startswith(protocol.MSG_SAVE_PROGRESS): # if the client is saving progress mid-stream
                        save_parts = req.split(protocol.SEPARATOR) # parse the save progress message
                        if len(save_parts) == 3: # validate the message format
                            client = current_client_map.get(addr) # get the Client object for this address
                            if client: # if the client was found
                                client.setCurrChapter(save_parts[1], int(save_parts[2])) # save the reading progress

                    else:
                        break  # unexpected message, exit the streaming loop

                # Done streaming (finished or stopped) — send END_OF_BOOK to signal the end
                protocol.send_message(conn, protocol.MSG_END_OF_BOOK) # notify the client that streaming has ended
                print(f"Ended streaming '{book_title}' to {addr}") # debug print line

            # ─── SAVE PROGRESS ───
            elif msg_type == protocol.MSG_SAVE_PROGRESS and len(parts) == 3 and authenticated: # if the client is saving reading progress (outside of streaming)
                book_title = parts[1] # extract the book title
                chapter = int(parts[2]) # extract the chapter index
                client = current_client_map.get(addr) # get the Client object for this address
                if client: # if the client was found
                    client.setCurrChapter(book_title, chapter) # save the reading progress
                    print(f"Saved progress: {client.getUserName()} → {book_title} ch.{chapter}") # debug print line

            # ─── GET PROGRESS ───
            elif msg_type == protocol.MSG_GET_PROGRESS and len(parts) == 2 and authenticated: # if the client is requesting their saved progress
                book_title = parts[1] # extract the book title
                client = current_client_map.get(addr) # get the Client object for this address
                chapter = -1 # default to -1 (no progress saved)
                if client: # if the client was found
                    chapter = client.getCurrChapter(book_title) # get the saved chapter index
                protocol.send_message(
                    conn,
                    f"{protocol.MSG_PROGRESS}{protocol.SEPARATOR}{chapter}" # send the progress back to the client
                )

            # ─── GET LAST BOOK ───
            elif msg_type == protocol.MSG_GET_LAST_BOOK and authenticated: # if the client is requesting the last book they were reading
                client = current_client_map.get(addr) # get the Client object for this address
                if client and client.lastBookRead: # if the client was found and has a last book
                    title = client.lastBookRead # get the title of the last book
                    chapter = client.getCurrChapter(title) # get the chapter index of the last book
                    protocol.send_message(
                        conn,
                        f"{protocol.MSG_LAST_BOOK}{protocol.SEPARATOR}{title}{protocol.SEPARATOR}{chapter}" # send the last book info to the client
                    )
                else: # if the client has no last book
                    protocol.send_message(
                        conn,
                        f"{protocol.MSG_LAST_BOOK}{protocol.SEPARATOR}NONE" # send NONE to the client
                    )

            else: # if the message type is unknown or the client is not authenticated
                protocol.send_message(conn, f"{protocol.MSG_ERROR}|Unknown command") # send an error message

    except Exception as e:
        print(f"Error handling client {addr}: {e}") # debug print line
    finally:
        current_client_map.pop(addr, None) # remove the client from the client map
        conn.close() # close the connection socket
        print(f"Connection closed: {addr}") # debug print line


def start_TCP_server():
    """A method to initialize and start the TCP server, accepting client connections in a loop."""
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM) # open a TCP socket
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1) # enable address reuse to allow quick restarts
    server_socket.bind(('', 12347)) # bind the socket to port 12347 on all interfaces
    server_socket.listen(5) # start listening for incoming connections (max 5 in the backlog)
    print("Server listening on port 12347...") # debug print line

    while True: # main TCP server loop — accept connections indefinitely
        conn, addr = server_socket.accept() # accept an incoming client connection
        thread = threading.Thread(target=handle_TCP_client, args=(conn, addr), daemon=True) # create a new thread to handle this client
        thread.start() # start the client handler thread




def start_server():
    """Main entry point: starts both the TCP and RUDP servers on separate threads."""
    print("Starting servers...") # debug print line
    # start a TCP server thread
    tcp_thread = threading.Thread(target=start_TCP_server, daemon=True) # create a daemon thread for the TCP server
    tcp_thread.start() # start the TCP server thread

    # start a RUDP server thread
    udp_thread = threading.Thread(target=start_UDP_server, daemon=True) # create a daemon thread for the RUDP server
    udp_thread.start() # start the RUDP server thread

    # keep the main thread alive so that the daemon threads don't get killed
    try:
        while True:
            time.sleep(1) # sleep to avoid busy-waiting
    except KeyboardInterrupt:
        print("Servers shutting down...") # debug print line

if __name__ == "__main__":
    start_server() # start the server when the script is run directly
