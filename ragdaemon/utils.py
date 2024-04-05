import hashlib
import os
import re
import subprocess
from pathlib import Path

from ragdaemon.errors import RagdaemonError


mentat_dir_path = Path.home() / ".mentat"


def hash_str(string: str) -> str:
    """Return the MD5 hash of the input string."""
    return hashlib.md5(string.encode()).hexdigest()


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
        if (Path(cwd) / p).exists() and not p.startswith(".ragdaemon")
    )


def get_git_diff(diff_args: str, cwd: str) -> str:
    args = ["git", "diff", "-U1"]
    if diff_args and diff_args != "DEFAULT":
        args += diff_args.split(" ")
    diff = subprocess.check_output(args, cwd=cwd, text=True)
    return diff


def parse_lines_ref(ref: str) -> set[int] | None:
    lines = set()
    for ref in ref.split(","):
        if "-" in ref:
            start, end = ref.split("-")
            lines.update(range(int(start), int(end) + 1))
        else:
            lines.add(int(ref))
    return lines or None


def parse_path_ref(ref: str) -> tuple[Path, set[int] | None]:
    match = re.match(r"^(.*?)(?::([0-9,\-]+))?$", ref)
    groups = match.groups()
    if len(groups) == 2 and all(groups):
        path_str, lines_ref = match.group(1), match.group(2)
        lines = parse_lines_ref(lines_ref)
    else:
        path_str, lines = ref, None
    return Path(path_str), lines


def get_document(ref: str, cwd: Path, type: str = "file") -> str:
    if type == "diff":
        if ":" in ref:
            diff_ref, lines_ref = ref.split(":", 1)
            lines = parse_lines_ref(lines_ref)
        else:
            diff_ref, lines = ref, None
        diff = get_git_diff(diff_ref, cwd)
        if lines:
            text = "\n".join(
                [line for i, line in enumerate(diff.split("\n")) if i + 1 in lines]
            )
        else:
            text = diff
        ref = f"git diff{'' if diff_ref == 'DEFAULT' else f' {diff_ref}'}"

    elif type in {"file", "chunk"}:
        path, lines = parse_path_ref(ref)
        if lines:
            text = ""
            with open(cwd / path, "r") as f:
                file_lines = f.read().split("\n")
            for line in sorted(lines):
                text += f"{line}:{file_lines[line - 1]}\n"
        else:
            with open(cwd / path, "r") as f:
                text = f.read()

    else:
        raise RagdaemonError(f"Invalid type: {type}")

    return f"{ref}\n{text}"
