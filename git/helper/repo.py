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

    def _checkout_branch_at_commit(self, branch, commit):
        self._repo.git.checkout("-f", branch)
        self._repo.git.reset("--hard", commit)
        logger.info(f"Repo {self._repo} Checkout to {branch}")

    def branches_contains_commit(self, commit: str) -> list[str]:
        logger.info(f"module = {self._repo}")
        logger.info(f"commit = {commit}")

        params = ["-a", "--contains", commit]

        branches: list[str] = self._repo.git.branch(*params)
        branches = branches.split("\n")
        branches = list(map(lambda x: x.strip(), branches))
        branches = list(filter(lambda x: "HEAD" not in x, branches))
        logger.info(f"branches = {branches}")
        branches = list(filter(lambda x: self._repo.git.rev_parse(x) == commit, branches))
        return branches

    def checkout_branch(self, branch):
        commit = self._repo.git.rev_parse("HEAD")
        branches = self.branches_contains_commit(commit)

        branches = list(map(lambda x: x.replace("remotes/origin/", "").strip(), branches))
        branches = list(set(branches))

        if not branches:
            logger.info(f"Not found branch in {self._repo}")
            return

        if branch in branches:
            logger.info(f"Repo {self._repo} Checkout to {branch}")
            self._repo.git.checkout(branch)
            return

        if len(branches) == 1:
            self._checkout_branch_at_commit(branches[0], commit)
            return

        branch_lines = [f"[{i}] - {x}" for i, x in enumerate(branches)]
        prompt = f"In module {self._repo}\nSelect branch or *n* if you don't want to checkout\n"
        prompt += "\n".join(branch_lines) + "\n"
        choice = input(prompt).strip()

        if choice == "n":
            return

        choice = int(choice)
        selected_branch = branches[choice]
        self._checkout_branch_at_commit(selected_branch, commit)

    def pull_branch(self, branch):
        logger.info(f"module = {self._repo}")
        try:
            self._repo.git.checkout(branch)
            self._repo.git.pull()
            logger.info(f"Pull code in {branch} done")
        except Exception as e:
            logger.debug(e)
            logger.info(f"There is no remote *{branch}")
