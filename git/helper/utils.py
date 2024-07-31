from collections.abc import Callable
from pygit2 import Branch, Object, Repository
from .log import logger
from typing import TypeVar, Optional
T = TypeVar('T')


def iMap(data: list, mapper) -> str:
    return ", ".join([mapper(key, value) for key, value in enumerate(data)])


def get_active_branch(repo: Repository):
    result = str(repo.head.shorthand).strip()
    logger.info("Active branch is : " + result)
    return result


def is_any_changes(repo: Repository):
    unstagedFiles = [item.a_path for item in repo.index.diff(None)]
    stagedFiles = [item.a_path for item in repo.index.diff("HEAD")]

    logger.debug(f"Check changes in repo {repo.working_tree_dir}")
    logger.debug(f"Unstaged files: {unstagedFiles}")
    logger.debug(f"stagedFiles : {stagedFiles}")

    return bool(unstagedFiles or stagedFiles)


def branches_containing_commit(repo: Repository, commit_sha: str, comparator) -> list[Branch]:
    # Get the commit object for the given SHA
    commit = repo.get(commit_sha)

    # List to hold branches containing the commit
    branches_with_commit = []

    # Check local branches
    for branch in repo.branches.local:
        branch_ref = repo.branches.local[branch]
        logger.debug(f"local target = {branch_ref.target}")
        branch_commit = repo.get(branch_ref.target)

        if comparator(repo, branch_commit, commit):
            branches_with_commit.append(branch_ref)

    # Check remote branches
    for remote in repo.branches.remote:
        logger.debug(f"remote = {remote}")
        if "HEAD" in remote:
            continue
        branch = repo.branches.remote[remote]
        target = branch.target
        logger.debug(f"remote_taget = {target}")
        branch_commit = repo.get(branch.target)
    #
        if comparator(repo, branch_commit, commit):
            branches_with_commit.append(branch)

    return branches_with_commit


def contains_commit(repo: Repository, branch_commit: Object, target_commit: Object):
    # Check if the branch contains the commit
    return repo.merge_base(branch_commit.id, target_commit.id) == target_commit.id


def equals_commit(repo: Repository, branch_commit: Object, target_commit: Object):
    return branch_commit.id == target_commit.id


def remove_duplicate(data: list[T], key_maker: Callable[[T], any], key_weight=Optional[Callable[[any, T], int]]) -> list[T]:
    output = dict()

    for item in data:
        key = key_maker(item)
        if key not in output:
            output[key] = item
        elif key_weight:
            old_item = output[key]
            old_weight = key_weight(key, old_item)
            new_weight = key_weight(key, item)
            if (new_weight > old_weight):
                output[key] = item

    return list(output.values())
