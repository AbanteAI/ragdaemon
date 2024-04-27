import json
from pathlib import Path
from typing import Any

from ragdaemon.annotators.chunker import Chunker
from ragdaemon.database import Database


class ChunkerLine(Chunker):
    name = "chunker_line"
    chunk_field_id = "chunks_line"

    def __init__(self, *args, lines_per_chunk=50, **kwargs):
        super().__init__(*args, **kwargs)
        self.n = lines_per_chunk

    async def chunk_file(
        self, cwd: Path, node: str, data: dict[str, Any], db: Database
    ):
        """Split text files into chunks N lines long.

        Chunker.annotate will generate a 'BASE' chunk from the lines
        not assigned to chunks as a hierarchical root of all chunks.
        Here we set aside the first N lines as the BASE chunk.
        """
        chunks = list[dict[str, str]]()
        file_lines = (cwd / Path(node)).read_text().splitlines()
        if len(file_lines) > self.n:
            chunks.append(
                {
                    "id": f"{node}:BASE",
                    "start_line": "1",
                    "end_line": str(self.n),
                }
            )  # First N lines is always the base chunk
            for i, start_line in enumerate(range(self.n + 1, len(file_lines), self.n)):
                chunks.append(
                    {
                        "id": f"{node}:chunk_{i + 1}",
                        "start_line": str(start_line),
                        "end_line": str(min(start_line + self.n - 1, len(file_lines))),
                    }
                )
        # Convert start/end to refs
        chunks = [
            {
                "id": chunk["id"],
                "ref": f"{node}:{chunk['start_line']}-{chunk['end_line']}",
            }
            for chunk in chunks
        ]
        # Save to db and graph
        metadatas = db.get(data["checksum"])["metadatas"][0]
        metadatas[self.chunk_field_id] = json.dumps(chunks)
        db.update(data["checksum"], metadatas=metadatas)
        data[self.chunk_field_id] = chunks
