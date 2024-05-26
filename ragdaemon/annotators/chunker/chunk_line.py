async def chunk_document(
    document: str, lines_per_chunk: int = 100
) -> list[dict[str, str]]:
    lines = document.split("\n")
    file = lines[0]
    file_lines = lines[1:]
    if not file_lines or not any(line for line in file_lines):
        return []

    chunks = list[dict[str, str]]()
    if len(file_lines) > lines_per_chunk:
        chunks.append(
            {
                "id": f"{file}:BASE",
                "ref": f"{file}:1-{lines_per_chunk}",
            }
        )  # First N lines is always the base chunk
        for i, start_line in enumerate(
            range(lines_per_chunk + 1, len(file_lines), lines_per_chunk)
        ):
            end_line = min(start_line + lines_per_chunk - 1, len(file_lines))
            chunks.append(
                {
                    "id": f"{file}:chunk_{i + 1}",
                    "ref": f"{file}:{start_line}-{end_line}",
                }
            )
    return chunks
