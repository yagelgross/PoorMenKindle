def divideChapter(book_name: str, chapter_content: str, chapter_index: int) -> list[str]:
    """ Divide a chapter into chunks of 500 characters each. """
    most_chars = 500
    packets = []

    total = (len(chapter_content) + most_chars - 1) // most_chars # the number of chunks needed
    for i in range(total): # create the chunks
        start = i * most_chars
        end = start + most_chars
        chunk = chapter_content[start:end]

        # CHUNK | BookName | ChapterNum | TotalChunks | CurrentChunkIndex | Text
        packet = f"CHUNK|{book_name}|{chapter_index}|{total}|{i}|{chapter_content[start:end]}" # pack the chunk into a packet
        packets.append(packet) # add the packet to the list
    return packets


class ChapterAssembler:
    """ An assembler that receives chunks of a chapter and assembles them into a single string."""
    def __init__(self):
        """Initialize the assembler. Call reset() to start a new chapter."""
        self.chunks_received = {}
        self.total_chunks_expected = -1
        self.book_name = ""
        self.chapter_index = -1

    def receive_chunk(self, packet_string: str) -> str | None:
        """Receive a chunk of a chapter and return (chapter_index, assembled_text) if complete. Otherwise, return None."""
        parts = packet_string.split('|', 5)
        if parts[0] != "CHUNK":
            return None

        req_book_name = parts[1] # received book name
        req_chap_idx = int(parts[2]) # received chapter index
        total_chunks = int(parts[3]) # total number of chunks expected for this chapter
        chunk_idx = int(parts[4]) # received chunk index
        text_data = parts[5] # received text data

        # reset state if we receive a chunk from a new chapter (or the first chunk of the first chapter)
        if self.total_chunks_expected == -1:
            self.book_name = req_book_name
            self.chapter_index = req_chap_idx
            self.total_chunks_expected = total_chunks

        # block chunks from other books or chapters, but adapt if the server moved to a newer chapter
        if self.book_name != req_book_name or self.chapter_index != req_chap_idx:
            # if the server moved on to a NEWER chapter from the same book, clear the old buffers and adapt!
            if self.book_name == req_book_name and req_chap_idx > self.chapter_index:
                print(f"Moving to new chapter {req_chap_idx}, dropping old chunks from ch.{self.chapter_index}")
                self.chunks_received.clear()
                self.chapter_index = req_chap_idx
                self.total_chunks_expected = total_chunks
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
        full_text = ""
        for i in range(self.total_chunks_expected):
            full_text += self.chunks_received[i]

        idx = self.chapter_index

        self.chunks_received.clear()
        self.total_chunks_expected = -1
        self.book_name = ""
        self.chapter_index = -1

        return idx, full_text