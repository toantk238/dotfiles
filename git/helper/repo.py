from pygit2 import Branch, Commit, Repository, Oid
from pygit2.index import ConflictCollection
from pygit2.repository import BranchType
from .utils import equals_commit, get_active_branch, iMap, is_any_changes, branches_containing_commit, remove_duplicate
from .log import logger


class MyRepo(object):

    _repo: Repository

    def __init__(self, path: str) -> None:
        self._repo = Repository(path)

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
        for module in self._repo.submodules:
            logger.info(f"syncing submodule {module.name}")
            try:
                module.update(init=True)
            except Exception as e:
                logger.error(e)

    def _checkout_branch_at_commit(self, branch: Branch, commit):
        commit_obj = self._repo.get(commit)
        branch_name = branch.shorthand.replace("origin/", "")
        new_branch = self._repo.branches.create(branch_name, commit_obj, force=True)
        self._repo.checkout(new_branch)

    def branches_contains_commit(self, commit: str) -> list[Branch]:
        logger.info(f"module = {self._repo.path}")
        logger.info(f"commit = {commit}")

        # params = ["-a", "--contains", commit]
        branches = branches_containing_commit(self._repo, commit, equals_commit)
        logger.info(f"branches = {iMap(branches, lambda _, x: str(x.shorthand))}")

        # branches: list[str] = self._repo.branches.remote.branche
        # branches = branches.split("\n")
        # branches = list(map(lambda x: x.strip(), branches))
        # branches = list(filter(lambda x: "HEAD" not in x, branches))
        # logger.info(f"branches = {branches}")
        # branches = list(filter(lambda x: self._repo.git.rev_parse(x) == commit, branches))
        return branches

    def checkout_branch(self, branch: str):
        commit = self._repo.head.target
        branches = self.branches_contains_commit(commit)
        branches = remove_duplicate(
            branches,
            lambda x: x.shorthand.replace("origin/", ""),
            lambda key, _: -1 if "origin" in key else 0
        )
        logger.info(f"distint_branches = {iMap(branches, lambda _, x: str(x.shorthand))}")

        if not branches:
            logger.info(f"Not found branch in {self._repo}")
            return

        found_branch = next(filter(lambda x: x.shorthand == branch, branches), None)

        if found_branch:
            logger.info(f"Repo {self._repo.path} --- checkout to {found_branch.name}")
            self._checkout_branch_at_commit(found_branch, commit)
            return

        if len(branches) == 1:
            self._checkout_branch_at_commit(branches[0], commit)
            return

        branch_lines = [f"[{i}] - {x.shorthand}" for i, x in enumerate(branches)]
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

    def get_commit_date_of_branch(self, branch: Branch):
        commit: Commit = self._repo.get(branch.target)
        commit_time = commit.commit_time
        logger.debug(f"commit_time of branch {branch.name} = {commit_time}")
        return commit_time

    def merge(self, branch):
        branch_type = BranchType.REMOTE if "origin" in branch else BranchType.LOCAL
        branch_ref = self._repo.lookup_branch(branch, branch_type)
        logger.debug(f"branch_ref = {branch_ref}")
        if not branch_ref:
            logger.error(f"Branch {branch} not found")
            exit(126)

        commit: Commit = self._repo.get(branch_ref.target)
        logger.debug(f"branch_target = {commit}")

        self._merge_commit(commit.id)

    def _merge_commit(self, commit_id: Oid | str) -> bool:
        # self._repo.merge_commits( self._repo.head.target , commit_id)
        self._repo.merge(commit_id)
        self.sync_submodules()
        conflicts = self._repo.index.conflicts
        if not conflicts:
            logger.info(f"No conflicts in {self._repo.path}")
            author = self._repo.default_signature
            self._repo.index.write()
            tree = self._repo.index.write_tree()
            new_commit = self._repo.create_commit(
                'HEAD',
                author,
                author,
                "Merge message",
                tree,
                [self._repo.head.target, commit_id])
            return True
        else:
            logger.warn(f"Conflicts in {self._repo.path}")
            return False

    def resolve_conflicts(self):
        conflicts = self._repo.index.conflicts
        if not conflicts:
            return

        submodules = {x.path: x for x in self.submodules}
        # logger.debug(f"sub_module_paths = {submodules}")

        for conflict in conflicts:
            (ancestor, our, their) = conflict
            if not ancestor:
                continue
            logger.info(f"ancestor = {ancestor}")
            logger.info(f"our = {our}")
            logger.info(f"their = {their}")
            if ancestor.path in submodules:
                submodule = submodules[ancestor.path]
                sub_repo = MyRepo(submodule.path)
                logger.info(f"submodule = {sub_repo}")
                logger.info(f"commitId = {their.oid}")
                merged_done = sub_repo._merge_commit(their.oid)
                if merged_done:
                    self._repo.index.add(ancestor.path)
                # Skip to merge sub_module. We can continue later
                continue


            # result = self._repo.merge_file_from_index(ancestor, our, their)
            # logger.debug(f"result = {result}")
