from git import Submodule, Repo
from .utils import get_active_branch, is_any_changes
from .log import logger


class MySubmodule(object):

    _repo: Repo
    _submodule: Submodule

    def __init__(self, submodule: Submodule) -> None:
        self._submodule = submodule
        self._repo = Repo(submodule.path)

    def get_active_branch(self) -> str:
        return get_active_branch(self._repo)

    def is_any_changes(self) -> bool:
        return is_any_changes(self._repo)

    def __repr__(self):
        return f"{self._submodule.name}"

    def pull_branch(self, branch):
        logger.info(f"module = {self._submodule}")
        try:
            self._repo.git.checkout(branch)
            self._repo.git.pull()
            logger.info(f"Pull code in {branch} done")
        except Exception as e:
            logger.error(e)
