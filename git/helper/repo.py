from git import Repo
from .utils import get_active_branch, is_any_changes
from .log import logger


class MyRepo(object):

    _repo: Repo

    def __init__(self, path: str) -> None:
        self._repo = Repo(path)

    def get_active_branch(self) -> str:
        return get_active_branch(self._repo)

    def is_any_changes(self) -> bool:
        return is_any_changes(self._repo)

    def __repr__(self):
        return f"{self._repo}"

    @property
    def submodules(self):
        return self._repo.submodules

    def sync_submodules(self):
        logger.info(f"syncing submodules in {self._repo}")
        self._repo.git.submodule('update', '--init', '-j', '8')

    def pull_branch(self, branch):
        logger.info(f"module = {self._repo}")
        try:
            self._repo.git.checkout(branch)
            self._repo.git.pull()
            logger.info(f"Pull code in {branch} done")
        except Exception as e:
            logger.debug(e)
            logger.info(f"There is no remote *{branch}")
