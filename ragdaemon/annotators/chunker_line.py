from ragdaemon.annotators.chunker import Chunker


class ChunkerLine(Chunker):
    name = "chunker_line"

    def __init__(self, *args, lines_per_chunk=50, **kwargs):
        super().__init__(*args, **kwargs)
        self.n = lines_per_chunk

    async def chunk_file(
        self, file_id: str, file_lines: list[str], verbose=False
    ) -> list[dict[str, str]]:
        """Split text files into chunks N lines long.

        Chunker.annotate will generate a 'BASE' chunk from the lines
        not assigned to chunks as a hierarchical root of all chunks.
        Here we set aside the first N lines as the BASE chunk.
        """
        if len(file_lines) < self.n:
            return []
        chunks = []
        for i, start_line in enumerate(range(self.n, len(file_lines), self.n)):
            chunks.append(
                {
                    "id": f"{file_id}:chunk_{i + 1}",
                    "start_line": start_line,
                    "end_line": min(start_line + self.n - 1, len(file_lines)),
                }
            )
        return chunks
