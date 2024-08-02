from .submodule import MySubmodule
from .log import logger
from .repo import MyRepo


class BigRepo(object):

    _repo: MyRepo

    def __init__(self, path) -> None:
        self._repo = MyRepo(path)

    def get_main_repo_branch(self) -> str:
        return self._repo.get_active_branch()

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
        self._repo.sync_submodules()
        main_repo_brach = self.get_main_repo_branch()
        for module in self.sub_module_repos():
            module.sync_branch(main_repo_brach)
            # module.pull_branch(main_repo_brach)

    def is_any_changes(self) -> bool:
        return self._repo.is_any_changes()

    def verify_before_push(self):
        for module in self.sub_module_repos():
            if not module.is_any_changes():
                continue
            logger.error(f"Module *{module}* have changes !")
            exit(1)

        if self.is_any_changes():
            logger.error(f"Main repo have changes !")
            exit(1)

        logger.info("All repos are ready to push !")

    def merge(self, branch: str):
        self._repo.merge(branch)

    def resolve_conflicts(self):
        self._repo.resolve_conflicts()
