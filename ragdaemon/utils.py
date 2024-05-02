import asyncio
import hashlib
import re
import subprocess
from base64 import b64encode
from pathlib import Path

from spice import Spice
from spice.models import GPT_4_TURBO, UnknownModel
from spice.spice import get_model_from_name

from ragdaemon.errors import RagdaemonError

mentat_dir_path = Path.home() / ".mentat"


semaphore = asyncio.Semaphore(100)


DEFAULT_CODE_EXTENSIONS = [
    ".py",
    ".js",
    ".java",
    ".html",
    ".css",
    ".sql",
    ".php",
    ".rb",
    ".sh",
    ".c",
    ".cpp",
    ".h",
    ".hpp",
    ".cs",
    ".go",
    ".ts",
    ".jsx",
    ".tsx",
    ".scss",
]


DEFAULT_COMPLETION_MODEL = GPT_4_TURBO


def hash_str(string: str) -> str:
    """Return the MD5 hash of the input string."""
    return hashlib.md5(string.encode()).hexdigest()


def basic_auth(username: str, password: str):
    token = b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
    return f"Basic {token}"


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
    if not match:
        return Path(ref), None
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
        diff = get_git_diff(diff_ref, str(cwd))
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
            if max(lines) > len(file_lines):
                raise RagdaemonError(f"{type} {ref} has invalid line numbers")
            for line in sorted(lines):
                text += f"{file_lines[line - 1]}\n"
        else:
            try:
                with open(cwd / path, "r") as f:
                    text = f.read()
            except UnicodeDecodeError:
                raise RagdaemonError(f"Not a text file: {path}")
    else:
        raise RagdaemonError(f"Invalid type: {type}")

    return f"{ref}\n{text}"


def truncate(document, embedding_model: str | None) -> tuple[str, float]:
    """Return an embeddable document, and what fraction was removed."""
    if embedding_model is None:
        return document, 0
    spice_model = get_model_from_name(embedding_model)
    if isinstance(spice_model, UnknownModel):
        raise RagdaemonError(f"Unrecognized embedding model: {embedding_model}")
    max_tokens = spice_model.context_length
    if max_tokens is None:
        return document, 0
    tokens = Spice().count_tokens(document, model=spice_model.name)
    original_tokens = tokens
    while tokens > max_tokens:
        truncate_ratio = (max_tokens / tokens) * 0.98  # Saw some errors with .99
        document = document[: int(len(document) * truncate_ratio)]
        tokens = Spice().count_tokens(document, model=spice_model.name)
    truncate_ratio = 1 - tokens / original_tokens
    if truncate_ratio > 0:
        label = "\n[TRUNCATED]"
        document = document[: -len(label)] + label
    return document, truncate_ratio


def lines_set_to_ref(lines: set[int]) -> str:
    if not lines:
        return ""
    refs = []
    low_to_high = sorted(lines)
    start = end = low_to_high[0]
    for i in low_to_high[1:]:
        if i == end + 1:
            end = i
        else:
            if start == end:
                refs.append(str(start))
            else:
                refs.append(f"{start}-{end}")
            start = end = i
    if start == end:
        refs.append(str(start))
    else:
        refs.append(f"{start}-{end}")
    return ",".join(refs)
