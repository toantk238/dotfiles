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


def branches_containing_commit(repo: Repository, commit_sha: str):
    # Get the commit object for the given SHA
    commit = repo.get(commit_sha)

    # List to hold branches containing the commit
    branches_with_commit = []

    # Check local branches
    for branch in repo.branches.local:
        branch_ref = repo.branches.local[branch]
        logger.info(f"local target = {branch_ref.target}")
        branch_commit = repo.get(branch_ref.target)

        if contains_commit(repo, branch_commit, commit):
            branches_with_commit.append(branch)

    # Check remote branches
    for remote in repo.branches.remote:
        logger.info(f"remote = {remote}")
        if "HEAD" in remote:
            continue
        branch = repo.branches.remote[remote]
        target = branch.target
        logger.info(f"remote_taget = {target}")
        branch_commit = repo.get(branch.target)
    #
        if contains_commit(repo, branch_commit, commit):
            branches_with_commit.append(remote)

    return branches_with_commit


def contains_commit(repo, branch_commit, target_commit):
    # Check if the branch contains the commit
    return repo.merge_base(branch_commit.id, target_commit.id) == target_commit.id
