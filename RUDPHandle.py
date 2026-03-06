def divideChapter(book_name: str, chapter_content: str, chapter_index: int) -> list[str]:
    most_chars = 500
    packets = []

    total = (len(chapter_content) + most_chars - 1) // most_chars
    for i in range(total):
        start = i * most_chars
        end = start + most_chars
        chunk = chapter_content[start:end]

        # CHUNK | BookName | ChapterNum | TotalChunks | CurrentChunkIndex | Text
        packet = f"CHUNK|{book_name}|{chapter_index}|{total}|{i}|{chapter_content[start:end]}"
        packets.append(packet)
    return packets


class ChapterAssembler:
    def __init__(self):
        self.chunks_received = {}
        self.total_chunks_expected = -1
        self.book_name = ""
        self.chapter_index = -1

    def receive_chunk(self, packet_string: str) -> str | None:
        parts = packet_string.split('|', 5)
        if parts[0] != "CHUNK":
            return None

        book_name = parts[1]
        chap_idx = int(parts[2])
        total_chunks = int(parts[3])
        chunk_idx = int(parts[4])
        text_data = parts[5]

        if chunk_idx not in self.chunks_received:
            self.chunks_received[chunk_idx] = text_data
            print(f"Received chunk {chunk_idx + 1}/{total_chunks}")
        if len(self.chunks_received) == self.total_chunks_expected:
            return self._assemble_chapter()
        return None

    def _assemble_chapter(self) -> str:
        full_text = ""
        for i in range(self.total_chunks_expected):
            full_text += self.chunks_received[i]
        self.chunks_received.clear()
        self.total_chunks_expected = -1

        return full_text