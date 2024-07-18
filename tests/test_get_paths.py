import gc
import os
import stat
import shutil
from pathlib import Path

from ragdaemon.get_paths import get_paths_for_directory, get_git_root_for_path


def test_get_paths_for_directory_git(cwd):
    cwd = cwd.resolve()
    paths = get_paths_for_directory(cwd)

    is_git_repo = get_git_root_for_path(cwd, raise_error=False)
    assert is_git_repo, "Not a git repository"

    assert paths == {
        Path(".gitignore"),
        Path("README.md"),
        Path("main.py"),
        Path("src/__init__.py"),
        Path("src/interface.py"),
        Path("src/operations.py"),
    }, "Paths are not equal"


def add_permissions(func, path, exc_info):
    """
    Error handler for ``shutil.rmtree``.

    If the error is due to an access error (read only file)
    it attempts to add write permission and then retries.

    If the error is because the file is being used by another process,
    it retries after a short delay.

    If the error is for another reason it re-raises the error.
    """

    gc.collect()  # Force garbage collection
    # Is the error an access error?
    if not os.access(path, os.W_OK):
        os.chmod(path, stat.S_IWUSR)
        func(path)
    else:
        raise


def test_get_paths_for_directory_without_git(cwd_git_diff):
    # Using the 'cwd_git_diff' fixture because it sets up a tempdir.
    cwd_git_diff = cwd_git_diff.resolve()
    git_dir = cwd_git_diff / ".git"
    shutil.rmtree(git_dir, onerror=add_permissions)

    is_git_repo = get_git_root_for_path(cwd_git_diff, raise_error=False)
    assert not is_git_repo, "Is a git repository"

    paths = get_paths_for_directory(cwd_git_diff)
    assert paths == {
        Path(".gitignore"),
        Path("README.md"),
        Path("hello.py"),
        Path("src/__init__.py"),
        Path("src/interface.py"),
        Path("src/operations.py"),
    }, "Paths are not equal"
