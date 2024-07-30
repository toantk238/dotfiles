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

    def branches_contains_head(self, is_remote: bool) -> list[str]:
        logger.info(f"module = {self._repo}")

        params = ["--contains", "HEAD"]
        if is_remote:
            params = ["-r"] + params

        branches = self._repo.git.branch(*params)
        branches = branches.split("\n")
        branches = list(filter(lambda x: "HEAD" not in x, branches))
        branches = list(map(lambda x: x.strip(), branches))
        return branches

    def checkout_branch(self, branch, is_remote: bool):
        branches = self.branches_contains_head(is_remote)

        if not branches:
            logger.info(f"Not found branch in {self._repo}")
            return

        if branch in branches:
            logger.info(f"Repo {self._repo} Checkout to {branch}")
            self._repo.git.checkout(branch)
            return

        branch_lines = [f"[{i}] - {x}" for i, x in enumerate(branches)]
        prompt = f"In module {self._repo}\nSelect branch or *n* if you don't want to checkout\n"
        prompt += "\n".join(branch_lines) + "\n"
        choice = input(prompt).strip()

        if choice == "n":
            return

        choice = int(choice)
        selected_branch = branches[choice]

        if is_remote:
            selected_branch = selected_branch.replace("origin/", "")
        
        self._repo.git.checkout("-f", selected_branch)
        logger.info(f"Repo {self._repo} Checkout to {selected_branch}")

    def pull_branch(self, branch):
        logger.info(f"module = {self._repo}")
        try:
            self._repo.git.checkout(branch)
            self._repo.git.pull()
            logger.info(f"Pull code in {branch} done")
        except Exception as e:
            logger.debug(e)
            logger.info(f"There is no remote *{branch}")
