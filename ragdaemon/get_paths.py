"""
These functions were almost directly copied from mentat/include_files.py in order to
support non-git projects in Mentat.
"""

import fnmatch
import logging
import os
import subprocess
from pathlib import Path
from typing import List, Optional, Set

from ragdaemon.errors import RagdaemonError


def is_file_text_encoded(abs_path: Path):
    """Checks if a file is text encoded."""
    try:
        # The ultimate filetype test
        with open(abs_path, "r") as f:
            f.read()
        return True
    except UnicodeDecodeError:
        return False


def get_git_root_for_path(path: Path, raise_error: bool = True) -> Optional[Path]:
    if os.path.isdir(path):
        dir_path = path
    else:
        dir_path = os.path.dirname(path)
    try:
        relative_path = (
            subprocess.check_output(
                [
                    "git",
                    "rev-parse",
                    "--show-prefix",
                ],
                cwd=os.path.realpath(dir_path),
                stderr=subprocess.DEVNULL,
            )
            .decode("utf-8")
            .strip()
        )
        # --show-toplevel doesn't work in some windows environment with posix paths,
        # like msys2, so we have to use --show-prefix instead
        git_root = os.path.abspath(
            os.path.join(dir_path, "../" * len(Path(relative_path).parts))
        )
        # call realpath to resolve symlinks, so all paths match
        return Path(os.path.realpath(git_root))
    except subprocess.CalledProcessError:
        if raise_error:
            logging.error(f"File {path} isn't part of a git project.")
            raise RagdaemonError()
        else:
            return


def get_non_gitignored_files(root: Path, visited: set[Path] = set()) -> Set[Path]:
    paths = set(
        # git returns / separated paths even on windows, convert so we can remove
        # glob_excluded_files, which have windows paths on windows
        Path(os.path.normpath(p))
        for p in filter(
            lambda p: p != "",
            subprocess.check_output(
                # -c shows cached (regular) files, -o shows other (untracked/new) files
                ["git", "ls-files", "-c", "-o", "--exclude-standard"],
                cwd=root,
                text=True,
                stderr=subprocess.DEVNULL,
            ).split("\n"),
        )
        # windows-safe check if p exists in path
        if Path(root / p).exists()
    )

    file_paths: Set[Path] = set()
    # We use visited to make sure we break out of any infinite loops symlinks might cause
    visited.add(root.resolve())
    for path in paths:
        # git ls-files returns directories if the directory is itself a git project;
        # so we recursively run this function on any directories it returns.
        if (root / path).is_dir():
            if (root / path).resolve() in visited:
                continue
            file_paths.update(
                root / path / inner_path
                for inner_path in get_non_gitignored_files(root / path, visited)
            )
        else:
            file_paths.add(path)
    return file_paths


def match_path_with_patterns(path: Path, patterns: Set[Path]) -> bool:
    """Check if the given absolute path matches any of the patterns.

    Args:
        `path` - An absolute path
        `patterns` - A set of absolute paths/glob patterns

    Return:
        A boolean flag indicating if the path matches any of the patterns
    """
    if not path.is_absolute():
        raise RagdaemonError(f"Path {path} is not absolute")
    for pattern in patterns:
        if not pattern.is_absolute():
            raise RagdaemonError(f"Pattern {pattern} is not absolute")
        # Check if the path is relative to the pattern
        if path.is_relative_to(pattern):
            return True
        # Check if the pattern is a glob pattern match
        if fnmatch.fnmatch(str(path), str(pattern)):
            return True
    return False


def get_paths_for_directory(
    path: Path,
    include_patterns: Set[Path] = set(),
    exclude_patterns: Set[Path] = set(),
    recursive: bool = True,
) -> Set[Path]:
    """Get all file paths in a directory.

    Args:
        `path` - An absolute path to a directory on the filesystem
        `include_patterns` - An iterable of absolute paths/glob patterns to include
        `exclude_patterns` - An iterable of absolute paths/glob patterns to exclude
        `recursive` - A boolean flag to recursive traverse child directories

    Return:
        A set of absolute file paths
    """
    paths: Set[Path] = set()

    if not path.exists():
        raise RagdaemonError(f"Path {path} does not exist")
    if not path.is_dir():
        raise RagdaemonError(f"Path {path} is not a directory")
    if not path.is_absolute():
        raise RagdaemonError(f"Path {path} is not absolute")

    for root, dirs, files in os.walk(path, topdown=True):
        root = Path(root)

        if get_git_root_for_path(root, raise_error=False):
            dirs[:] = list[str]()
            git_non_gitignored_paths = get_non_gitignored_files(root)
            for git_path in git_non_gitignored_paths:
                abs_git_path = root / git_path
                if not recursive and git_path.parent != Path("."):
                    continue
                if any(include_patterns) and not match_path_with_patterns(
                    abs_git_path, include_patterns
                ):
                    continue
                if any(exclude_patterns) and match_path_with_patterns(
                    abs_git_path, exclude_patterns
                ):
                    continue
                paths.add(abs_git_path)

        else:
            filtered_dirs: List[str] = []
            for dir_ in dirs:
                abs_dir_path = root.joinpath(dir_)
                if any(include_patterns) and not match_path_with_patterns(
                    abs_dir_path, include_patterns
                ):
                    continue
                if any(exclude_patterns) and match_path_with_patterns(
                    abs_dir_path, exclude_patterns
                ):
                    continue
                filtered_dirs.append(dir_)
            dirs[:] = filtered_dirs

            for file in files:
                abs_file_path = root.joinpath(file)
                if any(include_patterns) and not match_path_with_patterns(
                    abs_file_path, include_patterns
                ):
                    continue
                if any(exclude_patterns) and match_path_with_patterns(
                    abs_file_path, exclude_patterns
                ):
                    continue
                paths.add(abs_file_path)

            if not recursive:
                break
    paths = set(p.resolve() for p in paths if is_file_text_encoded(p))
    relative_paths = set(p.relative_to(path.resolve()) for p in paths)

    return relative_paths
