from contextlib import contextmanager
from pathlib import Path
from typing import Optional, Set

from docker.models.containers import Container

from ragdaemon.errors import RagdaemonError
from ragdaemon.get_paths import match_path_with_patterns


class FileInDocker:
    def __init__(self, container, path, mode):
        self.container = container
        self.path = path
        self.mode = mode
        self._content = None
        self._pos = 0

        if "r" in mode:
            result = self.container.exec_run(f"cat {self.path}")
            if result.exit_code != 0:
                if "No such file or directory" in result.stderr.decode("utf-8"):
                    raise FileNotFoundError(f"No such file exists: {self.path}")
                else:
                    raise IOError(
                        f"Failed to read file {self.path} in container: {result.stderr.decode('utf-8')}"
                    )
            self._content = result.output.decode("utf-8")

    def read(self):
        if self._content is None:
            raise IOError("File not opened in read mode")
        return self._content

    def write(self, data):
        if "w" not in self.mode:
            raise IOError("File not opened in write mode")
        result = self.container.exec_run(f"sh -c 'echo \"{data}\" > {self.path}'")
        if result.exit_code != 0:
            raise IOError(
                f"Failed to write file {self.path} in container: {result.stderr.decode('utf-8')}"
            )

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass


class DockerIO:
    def __init__(self, cwd: Path, container: Container):
        self.cwd = cwd
        self.container = container

    @contextmanager
    def open(self, path: Path, mode: str = "r"):
        file_path = self.cwd / path
        docker_file = FileInDocker(self.container, file_path, mode)
        yield docker_file

    def get_paths_for_directory(
        self, path: Optional[Path] = None, exclude_patterns: Set[Path] = set()
    ) -> Set[Path]:
        root = self.cwd if path is None else self.cwd / path
        if not self.is_git_repo(root):
            raise RagdaemonError(
                f"Path {path} is not a git repo. Ragdaemon DockerIO only supports git repos."
            )

        def get_non_gitignored_files(root: Path) -> Set[Path]:
            return set(
                Path(p)
                for p in filter(
                    lambda p: p != "",
                    self.container.exec_run(
                        ["git", "ls-files", "-c", "-o", "--exclude-standard"],
                        workdir=root,
                    )
                    .output.decode("utf-8")
                    .split("\n"),
                )
            )

        def is_text_encoded(path: Path) -> bool:
            try:
                with self.open(path) as f:
                    f.read()
                return True
            except UnicodeDecodeError:
                return False

        paths = set[Path]()
        for path in get_non_gitignored_files(root):
            if exclude_patterns:
                abs_path = (
                    self.container.exec_run(f"realpath {path}")
                    .output.decode("utf-8")
                    .strip()
                )
                if match_path_with_patterns(abs_path, exclude_patterns):
                    continue
            if not is_text_encoded(path):
                continue
            paths.add(path)
        return paths

    def is_git_repo(self, path: Optional[Path] = None):
        args = ["git", "ls-files", "--error-unmatch"]
        if path:
            args.append(f"{path}")
        try:
            result = self.container.exec_run(args, workdir=self.cwd)
            return result.exit_code == 0
        except Exception:
            return False

    def last_modified(self, path: Path) -> float:
        path = self.cwd / path
        result = self.container.exec_run(f"stat -c %Y {path}")
        if result.exit_code != 0:
            raise FileNotFoundError(f"No such file exists: {path}")
        return float(result.output.decode("utf-8"))

    def get_git_diff(self, diff_args: str) -> str:
        args = ["git", "diff", "-U1"]
        if diff_args and diff_args != "DEFAULT":
            args += diff_args.split(" ")
        result = self.container.exec_run(args)
        if result.exit_code != 0:
            raise IOError(f"Failed to get git diff: {result.stderr.decode('utf-8')}")
        return result.output.decode("utf-8")
