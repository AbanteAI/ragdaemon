import subprocess
from contextlib import contextmanager
from pathlib import Path
from typing import Optional, Set, Union

from docker.models.containers import Container

from ragdaemon.get_paths import get_paths_for_directory, get_git_root_for_path


class LocalIO:
    def __init__(self, cwd: Path):
        self.cwd = cwd

    @contextmanager
    def open(self, path: Path, mode: str = "r"):
        with open(self.cwd / path, mode) as file:
            yield file

    def get_paths_for_directory(
        self, path: Optional[Path] = None, exclude_patterns: Set[Path] = set()
    ):
        path = self.cwd if path is None else self.cwd / path
        return get_paths_for_directory(path, exclude_patterns=exclude_patterns)

    def get_git_root_for_path(
        self, path: Optional[Path] = None, raise_error: bool = False
    ):
        path = self.cwd if path is None else self.cwd / path
        return get_git_root_for_path(path, raise_error=raise_error)

    def last_modified(self, path: Path):
        return (self.cwd / path).stat().st_mtime

    def get_git_diff(self, diff_args: str) -> str:
        args = ["git", "diff", "-U1"]
        if diff_args and diff_args != "DEFAULT":
            args += diff_args.split(" ")
        diff = subprocess.check_output(args, cwd=self.cwd, text=True)
        return diff


class DockerIO:
    def __init__(self, cwd: Path, container: Container):
        self.cwd = cwd
        self.container = container

    @contextmanager
    def open(self, path: Path, mode: str = "r"):
        with self.container.exec_run(f"cat {self.cwd / path}") as exec_run:
            yield exec_run.output.decode("utf-8")

    def get_paths_for_directory(
        self, path: Optional[Path] = None, exclude_patterns: Set[Path] = set()
    ):
        raise NotImplementedError

    def get_git_root_for_path(
        self, path: Optional[Path] = None, raise_error: bool = False
    ):
        raise NotImplementedError

    def last_modified(self, path: Path):
        raise NotImplementedError

    def get_git_diff(self, diff_args: str) -> str:
        raise NotImplementedError


IO = Union[LocalIO, DockerIO]
