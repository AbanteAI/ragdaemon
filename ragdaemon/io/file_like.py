from typing import Protocol


class FileLike(Protocol):
    def read(self) -> str:
        ...

    def write(self, data: str) -> int:
        ...

    def __enter__(self) -> "FileLike":
        ...

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        ...
