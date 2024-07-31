from pygit2 import Repository
from .log import logger


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
