"""Small pygit2 helpers shared by the repo wrappers."""

from __future__ import annotations

from collections.abc import Callable

from pygit2 import Branch, Oid, Repository
from pygit2.enums import FileStatus

WT_CHANGES = (FileStatus.WT_MODIFIED | FileStatus.WT_DELETED | FileStatus.WT_TYPECHANGE
              | FileStatus.WT_RENAMED)
INDEX_CHANGES = (FileStatus.INDEX_NEW | FileStatus.INDEX_MODIFIED | FileStatus.INDEX_DELETED
                 | FileStatus.INDEX_RENAMED | FileStatus.INDEX_TYPECHANGE)

# Asked to pick one of `options`; returns the chosen index or None to skip.
Chooser = Callable[[str, list[str]], int | None]


def console_chooser(prompt: str, options: list[str]) -> int | None:
    print(prompt)
    for i, option in enumerate(options):
        print(f"  [{i}] {option}")
    answer = input("Pick a number, or press Enter to skip: ").strip().lower()
    if answer in ("", "n", "no"):
        return None
    try:
        index = int(answer)
    except ValueError:
        print(f"'{answer}' is not a number, skipping.")
        return None
    if not 0 <= index < len(options):
        print(f"{index} is out of range, skipping.")
        return None
    return index


def changed_paths(repo: Repository) -> list[str]:
    """Tracked paths with staged or unstaged changes (untracked files are ignored)."""
    status = repo.status(untracked_files="no")
    return sorted(path for path, flags in status.items() if flags & (WT_CHANGES | INDEX_CHANGES))


def current_branch(repo: Repository) -> str | None:
    """Short name of the checked-out branch, or None when HEAD is detached or unborn."""
    if repo.head_is_unborn or repo.head_is_detached:
        return None
    return repo.head.shorthand


def is_remote_branch(branch: Branch) -> bool:
    return branch.name.startswith("refs/remotes/")


def local_name(branch: Branch) -> str:
    """'feature' for both refs/heads/feature and refs/remotes/<remote>/feature."""
    if is_remote_branch(branch):
        return branch.shorthand[len(branch.remote_name) + 1:]
    return branch.shorthand


def all_branches(repo: Repository) -> list[Branch]:
    """Local branches first, then remote-tracking branches (skipping the symbolic <remote>/HEAD)."""
    branches: list[Branch] = [repo.branches.local[name] for name in repo.branches.local]
    for name in repo.branches.remote:
        if name.endswith("/HEAD"):
            continue
        branches.append(repo.branches.remote[name])
    return branches


def branches_pointing_at(repo: Repository, oid: Oid) -> list[Branch]:
    return [b for b in all_branches(repo) if b.target == oid]


def remote_branches_containing(repo: Repository, oid: Oid) -> list[Branch]:
    found = []
    for branch in all_branches(repo):
        if not is_remote_branch(branch):
            continue
        if repo.merge_base(branch.target, oid) == oid:
            found.append(branch)
    return found
