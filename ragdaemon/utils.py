import hashlib
import os
import subprocess
from pathlib import Path


def hash_str(string: str) -> str:
    """Return the MD5 hash of the input string."""
    return hashlib.md5(string.encode()).hexdigest()


def get_document(ref: str, cwd: Path) -> str:

    is_commit = ref.startswith("commit-") and not any(_ in ref for _ in "/:.")
    if is_commit:
        hexsha = ref.split("-")[1]
        message = subprocess.check_output(
            ["git", "log", "-1", "--pretty=%B", hexsha], cwd=cwd, text=True
        )
        diff = subprocess.check_output(
            ["git", "show", "--pretty=", "--name-only", hexsha], cwd=cwd, text=True
        )
        return f"{ref}: {message}\n{diff}"

    path, lines = parse_path_ref(ref)
    if lines:
        text = ""
        with open(cwd / path, "r") as f:
            file_lines = f.readlines()
        for line in sorted(lines):
            text += f"{line}:{file_lines[line - 1]}\n"
    else:
        with open(cwd / path, "r") as f:
            text = f.read()
    return f"{ref}\n{text}"
    

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


def parse_path_ref(ref: str) -> tuple[Path, set[int] | None]:
    if ":" in ref:
        path_str, lines_ref = ref.split(":", 1)
        lines = set()
        for ref in lines_ref.split(","):
            if "-" in ref:
                start, end = ref.split("-")
                lines.update(range(int(start), int(end) + 1))
            else:
                lines.add(int(ref))
    else:
        path_str, lines = ref, None
    return Path(path_str), lines
