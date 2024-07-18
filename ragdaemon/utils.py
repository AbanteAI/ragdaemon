import asyncio
import hashlib
import re
from base64 import b64encode
from pathlib import Path

from spice import Spice
from spice.models import GPT_4o_2024_05_13, Model, UnknownModel
from spice.spice import get_model_from_name

from ragdaemon.errors import RagdaemonError
from ragdaemon.io import IO

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


DEFAULT_COMPLETION_MODEL = GPT_4o_2024_05_13


def hash_str(string: str) -> str:
    """Return the MD5 hash of the input string."""
    return hashlib.md5(string.encode()).hexdigest()


def basic_auth(username: str, password: str):
    token = b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
    return f"Basic {token}"


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


def parse_diff_id(id: str) -> tuple[str, Path | None, set[int] | None]:
    if ":" in id:
        diff_ref, path_ref = id.split(":", 1)
        path, lines = parse_path_ref(path_ref)
    else:
        diff_ref, path, lines = id, None, None
    return diff_ref, path, lines


def get_document(
    ref: str, io: IO, type: str = "file", ignore_patterns: set[Path] = set()
) -> str:
    if type == "diff":
        if ":" in ref:
            diff_ref, lines_ref = ref.split(":", 1)
            lines = parse_lines_ref(lines_ref)
        else:
            diff_ref, lines = ref, None
        diff = io.get_git_diff(diff_ref)
        if lines:
            text = "\n".join(
                [line for i, line in enumerate(diff.split("\n")) if i + 1 in lines]
            )
        else:
            text = diff
        ref = f"git diff{'' if diff_ref == 'DEFAULT' else f' {diff_ref}'}"

    elif type == "directory":
        path = None if ref == "ROOT" else Path(ref)
        paths = sorted(
            [
                p.as_posix()
                for p in io.get_paths_for_directory(
                    path=path, exclude_patterns=ignore_patterns
                )
            ]
        )
        text = "\n".join(paths)

    elif type in {"file", "chunk"}:
        path, lines = parse_path_ref(ref)
        if lines:
            text = ""
            with io.open(path, "r") as f:
                file_lines = f.read().split("\n")
            if max(lines) > len(file_lines):
                raise RagdaemonError(f"{type} {ref} has invalid line numbers")
            for line in sorted(lines):
                text += f"{file_lines[line - 1]}\n"
        else:
            try:
                with io.open(path, "r") as f:
                    text = f.read()
            except UnicodeDecodeError:
                raise RagdaemonError(f"Not a text file: {path}")
    else:
        raise RagdaemonError(f"Invalid type: {type}")

    return f"{ref}\n{text}"


def truncate(
    document, model: str | Model | None = None, tokens: int | None = None
) -> tuple[str, float]:
    """Return an embeddable document, and what fraction was removed."""
    if model is None:
        return document, 0

    if isinstance(model, str):
        model = get_model_from_name(model)
        if isinstance(model, UnknownModel):
            raise RagdaemonError(f"Unrecognized model: {model}")
    max_tokens = model.context_length
    if tokens is not None:
        max_tokens = tokens if max_tokens is None else min(max_tokens, tokens)
    doc_tokens = Spice().count_tokens(document, model=model.name)
    if max_tokens is None or doc_tokens <= max_tokens:
        return document, 0

    original_tokens = doc_tokens
    while doc_tokens > max_tokens:
        truncate_ratio = (max_tokens / doc_tokens) * 0.98  # Saw some errors with .99
        document = document[: int(len(document) * truncate_ratio)]
        doc_tokens = Spice().count_tokens(document, model=model.name)
    truncate_ratio = 1 - doc_tokens / original_tokens
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


def match_refresh(refresh: str | bool, target: str) -> bool:
    if isinstance(refresh, bool):
        return refresh

    front_wildcard = refresh.startswith("*")
    back_wildcard = refresh.endswith("*")
    if front_wildcard and back_wildcard:
        return refresh[1:-1] in target
    elif front_wildcard:
        return target.endswith(refresh[1:])
    elif back_wildcard:
        return target.startswith(refresh[:-1])
    else:
        return refresh == target
