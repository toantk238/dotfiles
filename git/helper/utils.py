from git import Repo


def get_active_branch(repo: Repo):
    try:
        return repo.active_branch
    except:
        return None

def is_any_changes(repo: Repo):
    unstagedFiles = [item.a_path for item in repo.index.diff(None)]
    stagedFiles = [item.a_path for item in repo.index.diff("HEAD")]

    return bool(unstagedFiles or stagedFiles)
