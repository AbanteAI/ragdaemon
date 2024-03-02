import hashlib
from pathlib import Path


def hash_str(string: str) -> str:
    """Return the MD5 hash of the input string."""
    return hashlib.md5(string.encode()).hexdigest()


def get_document(_path: str | Path, _cwd: Path, file_lines: list[str] | None = None) -> str:
    _path = str(_path)
    if ":" in _path:
        _path, lines_ref = _path.split(':')
        if file_lines is None:
            with open(_cwd / _path, "r") as f:
                file_lines = f.readlines()
        ranges = lines_ref.split(',')
        text = ""
        for ref in ranges:
            if '-' in ref:
                _start, _end = ref.split('-')
                text += "\n".join(file_lines[int(_start)-1:int(_end)])
            elif ref.isdigit():
                text += file_lines[int(ref)]
    else:
        with open(_cwd / _path, "r") as f:
            text = f.read()
    return f"{_path}\n{text}"
