import hashlib
from pathlib import Path


ragdaemon_dir = Path.cwd() / ".ragdaemon"
ragdaemon_dir.mkdir(exist_ok=True)


def hash_str(string: str) -> str:
    """Return the MD5 hash of the input string."""
    return hashlib.md5(string.encode()).hexdigest()
