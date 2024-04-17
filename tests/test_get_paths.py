import shutil
from pathlib import Path

from ragdaemon.get_paths import get_paths_for_directory, get_git_root_for_path


def test_get_paths_for_directory_git(cwd):
    cwd = cwd.resolve()
    paths = get_paths_for_directory(cwd)

    is_git_repo = get_git_root_for_path(cwd, raise_error=False)
    assert is_git_repo, "Not a git repository"

    assert paths == {
        Path("README.md"),
        Path("main.py"),
        Path("src/__init__.py"),
        Path("src/interface.py"),
        Path("src/operations.py"),
    }, "Paths are not equal"


def test_get_paths_for_directory_without_git(git_history):
    # Using the 'git_history' fixture because it sets up a tempdir.
    git_history = git_history.resolve()
    git_dir = git_history / ".git"
    shutil.rmtree(git_dir)

    is_git_repo = get_git_root_for_path(git_history, raise_error=False)
    assert not is_git_repo, "Is a git repository"

    paths = get_paths_for_directory(git_history)
    assert paths == {
        Path(".gitignore"),
        Path(".ragdaemon/graph.json"),
        Path("README.md"),
        Path("hello.py"),
        Path("src/__init__.py"),
        Path("src/interface.py"),
        Path("src/operations.py"),
    }, "Paths are not equal"
