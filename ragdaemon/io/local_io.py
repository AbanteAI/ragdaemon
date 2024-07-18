import subprocess
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Optional, Set, Union
from types import TracebackType

from ragdaemon.get_paths import get_paths_for_directory
from ragdaemon.io.file_like import FileLike


class FileWrapper:
    def __init__(self, file: Any):
        self._file = file

    def read(self, size: int = -1) -> str:
        return self._file.read(size)

    def write(self, data: str) -> int:
        return self._file.write(data)

    def __enter__(self) -> "FileWrapper":
        return self

    def __exit__(
        self,
        exc_type: Union[type, None],
        exc_val: Union[BaseException, None],
        exc_tb: Union[TracebackType, None],
    ) -> None:
        self._file.__exit__(exc_type, exc_val, exc_tb)


class LocalIO:
    def __init__(self, cwd: Path | str):
        self.cwd = Path(cwd)

    @contextmanager
    def open(self, path: Path | str, mode: str = "r") -> Iterator[FileLike]:
        path = Path(path)
        with open(self.cwd / path, mode) as file:
            yield FileWrapper(file)

    def get_paths_for_directory(
        self, path: Optional[Path | str] = None, exclude_patterns: Set[Path] = set()
    ):
        path = self.cwd if path is None else self.cwd / path
        return get_paths_for_directory(path, exclude_patterns=exclude_patterns)

    def is_git_repo(self, path: Optional[Path | str] = None):
        args = ["git", "ls-files", "--error-unmatch"]
        if path:
            args.append(Path(path).as_posix())
        try:
            output = subprocess.run(args, cwd=self.cwd)
            return output.returncode == 0
        except subprocess.CalledProcessError:
            return False

    def last_modified(self, path: Path | str) -> float:
        return (self.cwd / path).stat().st_mtime

    def get_git_diff(self, diff_args: Optional[str] = None) -> str:
        args = ["git", "diff", "-U1"]
        if diff_args and diff_args != "DEFAULT":
            args += diff_args.split(" ")
        diff = subprocess.check_output(args, cwd=self.cwd, text=True)
        return diff

    def mkdir(self, path: Path | str, parents: bool = False, exist_ok: bool = False):
        (self.cwd / path).mkdir(parents=parents, exist_ok=exist_ok)

    def unlink(self, path: Path | str):
        (self.cwd / path).unlink()

    def rename(self, src: Path | str, dst: Path | str):
        (self.cwd / src).rename(self.cwd / dst)

    def exists(self, path: Path | str) -> bool:
        return (self.cwd / path).exists()
