import hashlib
import os
import subprocess
from pathlib import Path
from typing import Set


IGNORE_PATTERNS = [
    ".*",
    "node_modules",
    "venv",
    "__pycache__",
]


# Adapted from mentat.get_non_gitignored_files / is_file_text_encoded
def get_active_files(cwd: Path, visited: set[Path] = set()) -> Set[Path]:
    # All non-ignored and untracked files
    paths = set(
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
        if Path(cwd / p).exists()
    )
    # Including git submodules
    file_paths: Set[Path] = set()
    visited.add(cwd.resolve())
    for path in paths:
        if (cwd / path).is_dir():
            if (cwd / path).resolve() in visited:
                continue
            file_paths.update(
                cwd / path / inner_path
                for inner_path in get_active_files(cwd / path, visited)
            )
        else:
            file_paths.add(path)
    # Ignore patterns
    valid_files = set()
    for file in file_paths:
        if not any(
            file.match(pattern) or file.parts[0] == pattern
            for pattern in IGNORE_PATTERNS
        ):
            valid_files.add(file)
    # Only text files
    text_files: Set[Path] = set()
    for file in valid_files:
        try:
            with open(cwd / file, "r") as f:
                f.read()
            text_files.add(file)
        except UnicodeDecodeError:
            pass
    return text_files


checksum_cache = {}
def get_file_checksum(file: Path) -> str:
    """Calculate or retrieve the checksum of "<filename>:<file>".
    
    NOTE: FILE GRAPHS are cached by their CHECKSUM (.ragdaemon/graph_cache.json)
    and CHECKSUMS are cached by their FILENAME and LAST_MODIFIED (per session, below).
    """
    last_modified = file.stat().st_mtime
    identifier = f"{file}:{last_modified}"
    if identifier not in checksum_cache:
        return hashlib.md5(file.read_bytes()).hexdigest()
    return checksum_cache[identifier]

