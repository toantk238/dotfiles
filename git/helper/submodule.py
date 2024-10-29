from pygit2 import Submodule
from .repo import MyRepo
from .utils import logger


class MySubmodule(object):

    _repo: MyRepo
    _submodule: Submodule

    def __init__(self, submodule: Submodule) -> None:
        self._submodule = submodule
        self._repo = MyRepo(submodule.path)

    def get_active_branch(self) -> str:
        return self._repo.get_active_branch()

    def is_any_changes(self) -> bool:
        return self._repo.is_any_changes()

    def __repr__(self):
        return f"{self._submodule.name}"

    def pull_branch(self, branch):
        self._repo.pull_branch(branch)

    def sync_branch(self, branch):
        logger.info(f"Module {self._submodule.name}")
        active_branch = self.get_active_branch()

        if active_branch != "HEAD":
            return

        self._repo.checkout_branch(branch)
