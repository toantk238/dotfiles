from git import Repo
from .utils import get_active_branch, is_any_changes
from .submodule import MySubmodule
from .log import logger


class BigRepo(object):

    _repo: Repo

    def __init__(self, path) -> None:
        self._repo = Repo(path)

    def get_main_repo_branch(self) -> str:
        return get_active_branch(self._repo)

    def verify_local_state(self):
        main_repo_brach = self.get_main_repo_branch()
        for module in self.sub_module_repos():
            if not module.is_any_changes():
                continue

            module_branch = module.get_active_branch()

            if main_repo_brach != module_branch:
                logger.error(f"Repo {module} branch is not same as {main_repo_brach}. now is {module_branch}")
                logger.error(f"You should checkout/create a branch with name {main_repo_brach}")
                choice = input("Do you want to checkout remote branch? [y/n]: ")
                if (choice == 'y'):
                    module.pull_branch(main_repo_brach)

    def sub_module_repos(self) -> list[MySubmodule]:
        return list(map(lambda it: MySubmodule(it), self._repo.submodules))

    def sync_branch(self):
        main_repo_brach = self.get_main_repo_branch()
        for module in self.sub_module_repos():
            module.pull_branch(main_repo_brach)
