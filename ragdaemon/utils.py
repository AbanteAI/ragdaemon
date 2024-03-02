import hashlib


def hash_str(string: str) -> str:
    """Return the MD5 hash of the input string."""
    return hashlib.md5(string.encode()).hexdigest()
