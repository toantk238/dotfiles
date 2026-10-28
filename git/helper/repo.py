"""Thin wrapper around one pygit2.Repository (main repo or a submodule checkout)."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

from pygit2 import Branch, Commit, GitError, IndexEntry, Oid, Repository, Submodule
from pygit2.enums import FileMode, MergeAnalysis

from .log import logger
from .utils import (Chooser, branches_pointing_at, changed_paths, current_branch, is_remote_branch,
                    local_name, remote_branches_containing)


class NotARepository(Exception):
    pass


class GitRepo:

    def __init__(self, repo: Repository) -> None:
        self._repo = repo

    @classmethod
    def open(cls, path: str | Path) -> "GitRepo":
        try:
            return cls(Repository(str(path)))
        except GitError as exc:
            raise NotARepository(f"{path} is not a git repository") from exc

    @classmethod
    def from_submodule(cls, submodule: Submodule) -> "GitRepo":
        return cls(submodule.open())

    # ------------------------------------------------------------ state ---

    @property
    def workdir(self) -> Path:
        return Path(self._repo.workdir)

    @property
    def gitdir(self) -> Path:
        return Path(self._repo.path)

    def __repr__(self) -> str:
        return str(self.workdir)

    @property
    def head_id(self) -> Oid:
        return self._repo.head.peel(Commit).id

    @property
    def current_branch(self) -> str | None:
        return current_branch(self._repo)

    @property
    def is_detached(self) -> bool:
        return self._repo.head_is_detached

    def changed_paths(self) -> list[str]:
        return changed_paths(self._repo)

    def has_commit(self, oid: Oid) -> bool:
        return oid in self._repo

    def head_is_on_remote(self) -> bool:
        return bool(remote_branches_containing(self._repo, self.head_id))

    @property
    def submodules(self) -> list[Submodule]:
        return list(self._repo.submodules)

    def merge_in_progress(self) -> bool:
        return bool(self._repo.listall_mergeheads())

    def conflicts(self) -> list[tuple]:
        """Snapshot of (ancestor, ours, theirs) index entries; empty when clean.
        Re-reads the index first: an AI tool or the user may have run `git add`."""
        self._repo.index.read()
        conflicts = self._repo.index.conflicts
        return list(conflicts) if conflicts else []

    def fetch_all(self) -> bool:
        ok = True
        for remote in self._repo.remotes:
            logger.debug("%s: fetching %s", self, remote.name)
            try:
                remote.fetch()
            except GitError as exc:
                logger.warning("%s: fetch from %s failed: %s", self, remote.name, exc)
                ok = False
        return ok

    # ------------------------------------------------------- submodules ---

    def update_submodules(self) -> bool:
        """Init and check out every submodule at the commit recorded in the index."""
        ok = True
        for module in self._repo.submodules:
            if self._submodule_is_at_recorded_commit(module):
                continue  # libgit2's update would needlessly detach a branch checkout
            try:
                module.update(init=True)
            except GitError as exc:
                logger.error("Submodule %s: update failed: %s", module.path, exc)
                ok = False
        return ok

    def _submodule_is_at_recorded_commit(self, module: Submodule) -> bool:
        entry = self._repo.index[module.path] if module.path in self._repo.index else None
        wanted = entry.id if entry is not None else module.head_id
        try:
            return wanted is not None and module.open().head.target == wanted
        except GitError:
            return False  # not initialised yet

    def remove_all_submodules(self) -> None:
        for module in self.submodules:
            logger.info("Removing submodule %s", module.path)
            self._git("submodule", "deinit", "-f", "--", module.path)
            self._git("rm", "-f", "--", module.path)
            shutil.rmtree(self.gitdir / "modules" / module.name, ignore_errors=True)

    def _git(self, *args: str) -> None:
        subprocess.run(["git", *args], cwd=self.workdir, check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)

    # --------------------------------------------------------- branches ---

    def lookup_branch(self, name: str) -> Branch | None:
        """Local branch first, then remote-tracking (e.g. 'origin/feature')."""
        return self._repo.branches.get(name)

    def attach_head_to_branch(self, preferred: str | None, chooser: Chooser) -> bool:
        """Turn a detached HEAD into a branch checkout without moving the commit.

        Candidates are the branches whose tip is exactly HEAD. A branch named
        `preferred` wins; a single candidate is taken; otherwise `chooser` asks.
        A remote-tracking candidate becomes a new local branch with upstream set.
        Never moves an existing local branch. Returns True when HEAD ends on a branch.
        """
        if not self.is_detached:
            return True
        head = self.head_id
        candidates = self._dedupe(branches_pointing_at(self._repo, head))
        if not candidates:
            logger.warning("%s: detached at %s and no branch points at it; leaving as is",
                           self, str(head)[:10])
            return False

        chosen = next((b for b in candidates if local_name(b) == preferred), None)
        if chosen is None and len(candidates) == 1:
            chosen = candidates[0]
        if chosen is None:
            names = [b.shorthand for b in candidates]
            index = chooser(f"{self}: several branches point at {str(head)[:10]}", names)
            if index is None:
                logger.warning("%s: left detached at %s", self, str(head)[:10])
                return False
            chosen = candidates[index]

        return self._checkout_existing_or_tracking(chosen)

    @staticmethod
    def _dedupe(branches: list[Branch]) -> list[Branch]:
        """One entry per local name; a local branch shadows its remote-tracking twin."""
        by_name: dict[str, Branch] = {}
        for branch in branches:
            name = local_name(branch)
            if name not in by_name or (is_remote_branch(by_name[name]) and not is_remote_branch(branch)):
                by_name[name] = branch
        return list(by_name.values())

    def _checkout_existing_or_tracking(self, branch: Branch) -> bool:
        if not is_remote_branch(branch):
            self._repo.checkout(branch)
            logger.info("%s: now on branch %s", self, branch.shorthand)
            return True

        name = local_name(branch)
        head = self.head_id
        existing = self._repo.branches.local.get(name)
        if existing is not None:
            old_tip = existing.peel(Commit).id
            if self._repo.merge_base(old_tip, head) != old_tip:
                logger.warning("%s: local branch %s has commits not in %s (at %s), not touching it",
                               self, name, str(head)[:10], str(old_tip)[:10])
                return False
            # strictly behind: fast-forward it to HEAD, nothing is lost
            existing.set_target(head, f"gittool: fast-forward {name} to {branch.shorthand}")
            local = self._repo.branches.local[name]
            if local.upstream is None:
                local.upstream = branch
            self._repo.checkout(local)
            logger.info("%s: fast-forwarded branch %s from %s to %s", self, name, str(old_tip)[:10],
                        str(head)[:10])
            return True

        local = self._repo.branches.local.create(name, self._repo[head].peel(Commit))
        local.upstream = branch
        self._repo.checkout(local)
        logger.info("%s: created branch %s tracking %s", self, name, branch.shorthand)
        return True

    # ------------------------------------------------------------ merge ---

    def merge_branch(self, name: str) -> bool:
        """Merge `name` into HEAD. True when done (up to date, fast-forward or merge
        commit). False when conflicts were left in the index for resolution."""
        branch = self.lookup_branch(name)
        if branch is None:
            raise ValueError(f"branch '{name}' not found in {self}")
        dirty = self.changed_paths()
        if dirty:
            raise RuntimeError(f"{self} has uncommitted changes: {', '.join(dirty)}")
        if self.merge_in_progress():
            raise RuntimeError(f"{self} already has a merge in progress; resolve or abort it first")

        target = branch.peel(Commit).id
        into = self.current_branch or "detached HEAD"
        return self.merge_commit(target, f"Merge branch '{name}' into {into}")

    def merge_commit(self, target: Oid, message: str) -> bool:
        analysis, _ = self._repo.merge_analysis(target)
        if analysis & MergeAnalysis.UP_TO_DATE:
            logger.info("%s: already up to date", self)
            return True

        if analysis & MergeAnalysis.FASTFORWARD:
            self._repo.checkout_tree(self._repo[target].peel(Commit))
            if self.is_detached:
                self._repo.set_head(target)
            else:
                self._repo.head.set_target(target)
            logger.info("%s: fast-forwarded to %s", self, str(target)[:10])
            self.update_submodules()
            return True

        self._repo.merge(target)
        (self.gitdir / "MERGE_MSG").write_text(message + "\n")
        if self.conflicts():
            logger.warning("%s: conflicts in %s", self, ", ".join(self.conflicted_paths()))
            return False

        self.finish_merge()
        self.update_submodules()
        return True

    def finish_merge(self) -> Oid:
        """Commit the merge prepared in the index (HEAD + MERGE_HEADs) and clean up."""
        message = (self.gitdir / "MERGE_MSG").read_text().strip() if (self.gitdir / "MERGE_MSG").exists() else "Merge"
        parents: list = [self.head_id, *self._repo.listall_mergeheads()]
        index = self._repo.index
        index.write()
        tree = index.write_tree()
        signature = self._repo.default_signature
        oid = self._repo.create_commit("HEAD", signature, signature, message, tree, parents)
        self._repo.state_cleanup()
        logger.info("%s: merge committed as %s", self, str(oid)[:10])
        return oid

    def stage(self, path: str) -> None:
        self._repo.index.add(path)
        self._repo.index.write()

    def stage_blob(self, path: str, oid: Oid, mode: FileMode) -> None:
        """Record `oid` for `path` at stage 0, dropping any conflict entries for it."""
        index = self._repo.index
        index.add(IndexEntry(path, oid, FileMode(mode)))
        if index.conflicts and path in index.conflicts:
            del index.conflicts[path]
        index.write()

    def staged_id(self, path: str) -> Oid | None:
        index = self._repo.index
        index.read()
        entry = index[path] if path in index else None
        return entry.id if entry is not None else None

    def commit_index(self, message: str) -> Oid:
        """Plain commit of the current index on top of HEAD."""
        index = self._repo.index
        index.write()
        tree = index.write_tree()
        signature = self._repo.default_signature
        oid = self._repo.create_commit("HEAD", signature, signature, message, tree, [self.head_id])
        logger.info("%s: committed %s", self, str(oid)[:10])
        return oid

    def merge_source(self) -> str | None:
        """Name of the branch being merged, best effort: the MERGE_MSG gittool
        wrote, else a branch pointing at MERGE_HEAD."""
        msg_path = self.gitdir / "MERGE_MSG"
        if msg_path.exists():
            match = re.search(r"Merge branch '([^']+)'", msg_path.read_text())
            if match:
                return match.group(1)
        heads = self._repo.listall_mergeheads()
        if not heads:
            return None
        candidates = self._dedupe(branches_pointing_at(self._repo, heads[0]))
        return candidates[0].shorthand if candidates else None

    def resolve_branch_tip(self, name: str) -> Oid | None:
        """Tip of local `name`, else `<remote>/<name>` for any remote, else None."""
        branch = self.lookup_branch(name)
        if branch is None:
            short = name.split("/", 1)[-1] if "/" in name else name
            for remote in self._repo.remotes:
                branch = self.lookup_branch(f"{remote.name}/{short}")
                if branch is not None:
                    break
        return branch.peel(Commit).id if branch is not None else None

    def conflicted_paths(self) -> list[str]:
        return sorted({e.path for entry in self.conflicts() for e in entry if e is not None})
