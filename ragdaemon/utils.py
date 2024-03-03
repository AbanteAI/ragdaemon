import hashlib
import os
import subprocess
from pathlib import Path


def hash_str(string: str) -> str:
    """Return the MD5 hash of the input string."""
    return hashlib.md5(string.encode()).hexdigest()


def get_document(_path: str | Path, _cwd: Path) -> str:
    _path = str(_path)
    if ":" in _path:
        _path, lines_ref = _path.split(":")
        with open(_cwd / _path, "r") as f:
            file_lines = f.readlines()
        ranges = lines_ref.split(",")
        text = ""
        for ref in ranges:
            if "-" in ref:
                _start, _end = ref.split("-")
                text += "\n".join(file_lines[int(_start) - 1 : int(_end)])
            elif ref.isdigit():
                text += file_lines[int(ref)]
    else:
        with open(_cwd / _path, "r") as f:
            text = f.read()
    return f"{_path}\n{text}"


def get_non_gitignored_files(cwd: Path) -> set[Path]:
    return set(  # All non-ignored and untracked files
        Path(os.path.normpath(p))
        for p in filter(
            lambda p: p != "",
            subprocess.check_output(
                ["git", "ls-files", "-c", "-o", "--exclude-standard"],
                cwd=cwd,
                text=True,
                stderr=subprocess.DEVNULL,
            ).split("\n"),
        )
        if (Path(cwd) / p).exists()
    )
