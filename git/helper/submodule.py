from git import Submodule, Repo
from .utils import get_active_branch, is_any_changes


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

    def checkout_branch(self, branch):
        self._repo.git.fetch()
        self._repo.checkout(branch)
        self._repo.git.pull()
