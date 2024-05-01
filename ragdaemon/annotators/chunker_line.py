from typing import Any, Coroutine

from ragdaemon.annotators.chunker import Chunker


class ChunkerLine(Chunker):
    name = "chunker_line"
    chunk_field_id = "chunks_line"

    def __init__(self, *args, lines_per_chunk=50, **kwargs):
        super().__init__(*args, **kwargs)
        self.n = lines_per_chunk

    async def chunk_document(self, document: str) -> list[dict[str, Any]]:
        lines = document.split("\n")
        file = lines[0]
        file_lines = lines[1:]
        if not file_lines or not any(line for line in file_lines):
            return []

        chunks = list[dict[str, Any]]()
        if len(file_lines) > self.n:
            chunks.append(
                {
                    "id": f"{file}:BASE",
                    "start_line": "1",
                    "end_line": str(self.n),
                }
            )  # First N lines is always the base chunk
            for i, start_line in enumerate(range(self.n + 1, len(file_lines), self.n)):
                chunks.append(
                    {
                        "id": f"{file}:chunk_{i + 1}",
                        "start_line": str(start_line),
                        "end_line": str(min(start_line + self.n - 1, len(file_lines))),
                    }
                )
        # Convert start/end to refs
        return [
            {
                "id": chunk["id"],
                "ref": f"{file}:{chunk['start_line']}-{chunk['end_line']}",
            }
            for chunk in chunks
        ]
