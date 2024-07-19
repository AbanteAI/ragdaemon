import io
import os
import tarfile
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional, Set

from docker.models.containers import Container

from ragdaemon.errors import RagdaemonError
from ragdaemon.get_paths import match_path_with_patterns
from ragdaemon.io.file_like import FileLike


class FileInDocker(FileLike):
    def __init__(self, container, path, mode):
        self.container = container
        self.path = path
        self.mode = mode
        self._content = None

        if "r" in mode:
            result = self.container.exec_run(f"cat /{self.path}")
            if result.exit_code != 0:
                if "No such file or directory" in result.output.decode("utf-8"):
                    raise FileNotFoundError(f"No such file exists: {self.path}")
                else:
                    raise IOError(
                        f"Failed to read file {self.path} in container: {result.stderr.decode('utf-8')}"
                    )
            self._content = result.output.decode("utf-8")

    def read(self, size: int = -1) -> str:
        if self._content is None:
            raise IOError("File not opened in read mode")
        return self._content if size == -1 else self._content[:size]

    def write(self, data: str) -> int:
        if "w" not in self.mode:
            raise IOError("File not opened in write mode")
        
        with tempfile.NamedTemporaryFile(delete=False) as temp_file:
            temp_file.write(data.encode('utf-8'))
            temp_file_path = temp_file.name
        
        # Create a tar archive of the temporary file
        tar_stream = io.BytesIO()
        with tarfile.open(fileobj=tar_stream, mode='w') as tar:
            tar.add(temp_file_path, arcname=os.path.basename(self.path))
        tar_stream.seek(0)

        # Put the archive into the container
        self.container.put_archive(os.path.dirname(self.path), tar_stream)

        # Clean up the temporary file
        os.remove(temp_file_path)

        return len(data)



    def __enter__(self) -> "FileInDocker":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        pass


class DockerIO:
    def __init__(self, cwd: Path | str, container: Container):
        self.cwd = Path(cwd)
        self.container = container

    @contextmanager
    def open(self, path: Path | str, mode: str = "r") -> Iterator[FileLike]:
        path = Path(path)
        file_path = self.cwd / path
        docker_file = FileInDocker(self.container, file_path, mode)
        yield docker_file

    def get_paths_for_directory(
        self, path: Optional[Path | str] = None, exclude_patterns: Set[Path] = set()
    ) -> Set[Path]:
        root = self.cwd if path is None else self.cwd / path
        if not self.is_git_repo(path):
            raise RagdaemonError(
                f"Path {root} is not a git repo. Ragdaemon DockerIO only supports git repos."
            )

        def get_non_gitignored_files(root: Path) -> Set[Path]:
            return set(
                Path(p)
                for p in filter(
                    lambda p: p != "",
                    self.container.exec_run(
                        ["git", "ls-files", "-c", "-o", "--exclude-standard"],
                        workdir=f"/{root.as_posix()}",
                    )
                    .output.decode("utf-8")
                    .split("\n"),
                )
            )

        files = set[Path]()
        for file in get_non_gitignored_files(root):
            if exclude_patterns:
                abs_path = (
                    self.container.exec_run(f"realpath {file}")
                    .output.decode("utf-8")
                    .strip()
                )
                if match_path_with_patterns(abs_path, exclude_patterns):
                    continue
            try:
                with self.open(file) as f:
                    f.read()
            except FileNotFoundError:
                continue  # File was deleted
            except UnicodeDecodeError:
                continue  # File is not text-encoded
            files.add(file)
        return files

    def is_git_repo(self, path: Optional[Path | str] = None):
        root = self.cwd if path is None else self.cwd / path
        args = ["git", "ls-files", "--error-unmatch"]
        try:
            result = self.container.exec_run(args, workdir=f"/{root.as_posix()}")
            return result.exit_code == 0
        except Exception:
            return False

    def last_modified(self, path: Path | str) -> float:
        path = self.cwd / path
        result = self.container.exec_run(f"stat -c %Y {path}")
        if result.exit_code != 0:
            raise FileNotFoundError(f"No such file exists: {path}")
        return float(result.output.decode("utf-8"))

    def get_git_diff(self, diff_args: Optional[str] = None) -> str:
        args = ["git", "diff", "-U1"]
        if diff_args and diff_args != "DEFAULT":
            args += diff_args.split(" ")
        result = self.container.exec_run(args, workdir=f"/{self.cwd}")
        if result.exit_code != 0:
            raise IOError(f"Failed to get git diff: {result.output.decode('utf-8')}")
        return result.output.decode("utf-8")

    def mkdir(self, path: Path | str, parents: bool = False, exist_ok: bool = False):
        result = self.container.exec_run(f"mkdir -p {self.cwd / path}")
        if result.exit_code != 0:
            raise IOError(
                f"Failed to make directory {self.cwd / path} in container: {result.output.decode('utf-8')}"
            )

    def unlink(self, path: Path | str):
        result = self.container.exec_run(f"rm {self.cwd / path}")
        if result.exit_code != 0:
            raise IOError(
                f"Failed to unlink {self.cwd / path} in container: {result.output.decode('utf-8')}"
            )

    def rename(self, src: Path | str, dst: Path | str):
        result = self.container.exec_run(f"mv {self.cwd / src} {self.cwd / dst}")
        if result.exit_code != 0:
            raise IOError(
                f"Failed to rename {self.cwd / src} to {self.cwd / dst} in container: {result.output.decode('utf-8')}"
            )

    def exists(self, path: Path | str) -> bool:
        result = self.container.exec_run(f"test -e {self.cwd / path}")
        return result.exit_code == 0
