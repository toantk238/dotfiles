from git import Repo
from .log import logger


def get_active_branch(repo: Repo):
    try:
        return repo.active_branch
    except:
        return None


def is_any_changes(repo: Repo):
    unstagedFiles = [item.a_path for item in repo.index.diff(None)]
    stagedFiles = [item.a_path for item in repo.index.diff("HEAD")]

    logger.debug(f"Check changes in repo {repo.working_tree_dir}")
    logger.debug(f"Unstaged files: {unstagedFiles}")
    logger.debug(f"stagedFiles : {stagedFiles}")

    return bool(unstagedFiles or stagedFiles)
