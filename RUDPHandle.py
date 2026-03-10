def divideChapter(book_name: str, chapter_content: str, chapter_index: int) -> list[str]:
    """ Divide a chapter into chunks of 500 characters each. """
    most_chars = 500 # the maximum number of characters in a chunk, since we may have hebrew or special characters,
                    # there might be 2 bytes required per char, so 500 is a safe bet.
    packets = []

    total = (len(chapter_content) + most_chars - 1) // most_chars # the number of chunks needed
    for i in range(total): # create the chunks
        start = i * most_chars # the starting index of the current chunk
        end = start + most_chars # the ending index of the current chunk

        # CHUNK | BookName | ChapterNum | TotalChunks | CurrentChunkIndex | Text
        packet = f"CHUNK|{book_name}|{chapter_index}|{total}|{i}|{chapter_content[start:end]}" # pack the chunk into a packet
        packets.append(packet) # add the packet to the list
    return packets


class ChapterAssembler:
    """ An assembler that receives chunks of a chapter and assembles them into a single string."""
    def __init__(self):
        """Initialize the assembler. Call reset() to start a new chapter."""
        self.chunks_received = {} # a dictionary to store received chunks
        self.total_chunks_expected = -1 # the total number of chunks expected for this chapter (initialized to -1)
        self.book_name = "" # the name of the book
        self.chapter_index = -1 # the index of the chapter (initialized to -1)

    def receive_chunk(self, packet_string: str) -> tuple[int, str] | None:
        """Receive a chunk of a chapter and return (chapter_index, assembled_text) if complete. Otherwise, return None."""
        parts = packet_string.split('|', 5) # split the packet into parts according to the known format
        if parts[0] != "CHUNK": # check if the packet is a chunk
            return None

        req_book_name = parts[1] # received book name
        req_chap_idx = int(parts[2]) # received chapter index
        total_chunks = int(parts[3]) # total number of chunks expected for this chapter
        chunk_idx = int(parts[4]) # received chunk index
        text_data = parts[5] # received text data

        # reset state if we receive a chunk from a new chapter (or the first chunk of the first chapter)
        if self.total_chunks_expected == -1: # reset state if we haven't received any chunks yet
            self.book_name = req_book_name # store the book name
            self.chapter_index = req_chap_idx # store the chapter index
            self.total_chunks_expected = total_chunks # store the total number of chunks expected

        # block chunks from other books or chapters, but adapt if the server moved to a newer chapter
        if self.book_name != req_book_name or self.chapter_index != req_chap_idx:
            # if the server moved on to a NEWER chapter from the same book, clear the old buffers and adapt!
            if self.book_name == req_book_name and req_chap_idx > self.chapter_index:
                print(f"Moving to new chapter {req_chap_idx}, dropping old chunks from ch.{self.chapter_index}")
                self.chunks_received.clear() # clear the old chunks
                self.chapter_index = req_chap_idx # update the chapter index
                self.total_chunks_expected = total_chunks # update the total number of chunks remaining
            else:
                return None

        # if we haven't received this chunk yet, store it
        if chunk_idx not in self.chunks_received:
            self.chunks_received[chunk_idx] = text_data
            print(f"Received chunk {chunk_idx + 1}/{total_chunks}")

        # test if we have all the chunks of the current chapter
        if len(self.chunks_received) == self.total_chunks_expected:
            return self._assemble_chapter()

        return None

    def _assemble_chapter(self) -> tuple[int, str] | None:
        full_text = "" # the assembled text
        for i in range(self.total_chunks_expected): # concatenate the chunks
            full_text += self.chunks_received[i]

        idx = self.chapter_index # return the chapter index

        self.chunks_received.clear() # clear the chunks dictionary
        self.total_chunks_expected = -1 # reset the total number of chunks expected
        self.book_name = "" # reset the book name
        self.chapter_index = -1 # reset the chapter index

        return idx, full_text # return the assembled chapter and its index