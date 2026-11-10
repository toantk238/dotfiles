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


FETCH_JOBS = 8  # `git fetch -j`: parallel remotes / submodules


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
        """`git fetch --all -j 8`: every remote, in parallel."""
        return self._fetch("--all")

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
        chosen = self._pick_branch(candidates, preferred, chooser, head)
        if chosen is None:
            logger.warning("%s: left detached at %s", self, str(head)[:10])
            return False
        return self._checkout_existing_or_tracking(chosen, head)

    def branch_at(self, oid: Oid, preferred: str | None, chooser: Chooser) -> Branch | None:
        """A branch whose tip is exactly `oid` that `check_out_at` can land on (a local
        twin of a remote candidate must be absent or behind `oid`). Picked like
        `attach_head_to_branch`; None when there is none or the chooser skips."""
        candidates = [b for b in self._dedupe(branches_pointing_at(self._repo, oid))
                      if self._can_land_on(b, oid)]
        if not candidates:
            return None
        return self._pick_branch(candidates, preferred, chooser, oid)

    def check_out_at(self, branch: Branch, oid: Oid) -> bool:
        """Check out `branch` (from `branch_at`) so HEAD ends on a local branch at `oid`."""
        ok = self._checkout_existing_or_tracking(branch, oid)
        if ok:
            self.update_submodules()
        return ok

    def _pick_branch(self, candidates: list[Branch], preferred: str | None, chooser: Chooser,
                     oid: Oid) -> Branch | None:
        chosen = next((b for b in candidates if local_name(b) == preferred), None)
        if chosen is None and len(candidates) == 1:
            chosen = candidates[0]
        if chosen is None:
            names = [b.shorthand for b in candidates]
            index = chooser(f"{self}: several branches point at {str(oid)[:10]}", names)
            chosen = candidates[index] if index is not None else None
        return chosen

    def _can_land_on(self, branch: Branch, oid: Oid) -> bool:
        if not is_remote_branch(branch):
            return True
        existing = self._repo.branches.local.get(local_name(branch))
        return existing is None or self.contains(oid, existing.peel(Commit).id)

    @staticmethod
    def _dedupe(branches: list[Branch]) -> list[Branch]:
        """One entry per local name; a local branch shadows its remote-tracking twin."""
        by_name: dict[str, Branch] = {}
        for branch in branches:
            name = local_name(branch)
            if name not in by_name or (is_remote_branch(by_name[name]) and not is_remote_branch(branch)):
                by_name[name] = branch
        return list(by_name.values())

    def _checkout_existing_or_tracking(self, branch: Branch, tip: Oid) -> bool:
        """Check out `branch`, whose tip is `tip`; a remote-tracking one becomes a
        local branch at `tip` (created, or fast-forwarded when strictly behind)."""
        if not is_remote_branch(branch):
            self._repo.checkout(branch)
            logger.info("%s: now on branch %s", self, branch.shorthand)
            return True

        name = local_name(branch)
        existing = self._repo.branches.local.get(name)
        if existing is not None:
            old_tip = existing.peel(Commit).id
            if not self.contains(tip, old_tip):
                logger.warning("%s: local branch %s has commits not in %s (at %s), not touching it",
                               self, name, str(tip)[:10], str(old_tip)[:10])
                return False
            # strictly behind: fast-forward it to the tip, nothing is lost
            existing.set_target(tip, f"gittool: fast-forward {name} to {branch.shorthand}")
            local = self._repo.branches.local[name]
            if local.upstream is None:
                local.upstream = branch
            self._repo.checkout(local)
            logger.info("%s: fast-forwarded branch %s from %s to %s", self, name, str(old_tip)[:10],
                        str(tip)[:10])
            return True

        local = self._repo.branches.local.create(name, self._repo[tip].peel(Commit))
        local.upstream = branch
        self._repo.checkout(local)
        logger.info("%s: created branch %s tracking %s", self, name, branch.shorthand)
        return True

    def local_branch_name(self, name: str) -> str:
        """'dev' for 'origin/dev' when that is a remote-tracking branch, else `name`."""
        branch = self.lookup_branch(name)
        return local_name(branch) if branch is not None else name

    # ------------------------------------------------------------ merge ---

    def branch_tip(self, name: str) -> Oid:
        """Tip of local or remote-tracking branch `name`; ValueError when missing."""
        branch = self.lookup_branch(name)
        if branch is None:
            raise ValueError(f"branch '{name}' not found in {self}")
        return branch.peel(Commit).id

    def ensure_can_merge(self) -> None:
        """RuntimeError unless the tree is clean and no merge is in progress."""
        dirty = self.changed_paths()
        if dirty:
            raise RuntimeError(f"{self} has uncommitted changes: {', '.join(dirty)}")
        if self.merge_in_progress():
            raise RuntimeError(f"{self} already has a merge in progress; resolve or abort it first")

    def gitlink(self, commit: Oid, path: str) -> Oid | None:
        """Submodule commit recorded at `path` in `commit`'s tree, None if not a submodule there."""
        try:
            entry = self._repo[commit].peel(Commit).tree[path]
        except KeyError:
            return None
        return entry.id if entry.filemode == FileMode.COMMIT else None

    def merge_conflicts_with(self, target: Oid) -> list[str]:
        """Paths that merging `target` into HEAD would leave conflicted (in memory, nothing touched)."""
        index = self._repo.merge_commits(self.head_id, target)
        if not index.conflicts:
            return []
        return sorted({e.path for entry in index.conflicts for e in entry if e is not None})

    def merge_commit(self, target: Oid, message: str, pinned: dict[str, Oid] | None = None) -> bool:
        """Merge `target` into HEAD. True when done (up to date, fast-forward or merge
        commit). False when conflicts were left in the index for resolution.

        `pinned`: submodule path -> commit the result must record (submodule checkouts
        already merged); staged over whatever the tree merge picked."""
        pinned = pinned or {}
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
            moved = [path for path, oid in pinned.items() if self.gitlink(target, path) != oid]
            for path in moved:
                self.stage_blob(path, pinned[path], FileMode.COMMIT)
            if moved:
                self.commit_index(f"Update submodules to their merged commits: {', '.join(moved)}")
            self.update_submodules()
            return True

        self._repo.merge(target)
        (self.gitdir / "MERGE_MSG").write_text(message + "\n")
        for path, oid in pinned.items():
            self.stage_blob(path, oid, FileMode.COMMIT)
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

    # -------------------------------------------------------------- prs ---

    def default_branch(self, configured: str | None = None, remote: str = "origin") -> str | None:
        """The branch PRs target: `<remote>/HEAD`, else `configured` (e.g. the
        .gitmodules `branch`), else main/master, if `<remote>/<name>` exists."""
        prefix = f"refs/remotes/{remote}/"
        ref = self._repo.references.get(f"{prefix}HEAD")
        target = ref.target if ref is not None else None
        if isinstance(target, str) and target.startswith(prefix):
            return target[len(prefix):]
        for name in (configured, "main", "master"):
            if name and self.lookup_branch(f"{remote}/{name}") is not None:
                return name
        return None

    def remote_tip(self, branch: str, remote: str = "origin") -> Oid | None:
        found = self.lookup_branch(f"{remote}/{branch}")
        return found.peel(Commit).id if found is not None else None

    def commits_since(self, base_tip: Oid) -> list[Commit]:
        """Commits reachable from HEAD but not from `base_tip`, newest first."""
        walker = self._repo.walk(self.head_id)
        walker.hide(base_tip)
        return list(walker)

    def contains(self, tip: Oid, oid: Oid) -> bool:
        """True when `oid` is reachable from `tip`."""
        return tip == oid or self._repo.merge_base(tip, oid) == oid

    def has_changes_of(self, tip: Oid, oid: Oid) -> bool:
        """True when `tip` already holds the code of `oid`: `oid` is reachable from
        it, or merging `oid` into `tip` would change nothing (squash merges,
        cherry-picks, rebases)."""
        if self.contains(tip, oid):
            return True
        try:
            index = self._repo.merge_commits(tip, oid)
        except GitError:
            return False
        if index.conflicts:
            return False
        return index.write_tree(self._repo) == self._repo[tip].peel(Commit).tree_id

    def branch_checkout_tip(self, name: str, remote: str = "origin") -> Oid | None:
        """The commit `checkout_branch(name)` would land on: `<remote>/<name>` when
        there is no local branch or the local one is strictly behind it, else the
        local tip. None when the branch exists nowhere."""
        local = self._repo.branches.local.get(name)
        remote_tip = self.remote_tip(name, remote)
        if local is None:
            return remote_tip
        local_tip = local.peel(Commit).id
        if remote_tip is not None and self.contains(remote_tip, local_tip):
            return remote_tip
        return local_tip

    def checkout_branch(self, name: str, remote: str = "origin") -> None:
        """Check out local branch `name`, creating it from `<remote>/<name>` or
        fast-forwarding it there first (see `branch_checkout_tip`)."""
        tip = self.branch_checkout_tip(name, remote)
        if tip is None:
            raise ValueError(f"{self}: no branch '{name}' locally or on {remote}")
        local = self._repo.branches.local.get(name)
        if local is None:
            local = self._repo.branches.local.create(name, self._repo[tip].peel(Commit))
            upstream = self.lookup_branch(f"{remote}/{name}")
            if upstream is not None:  # always: a missing local branch means tip came from it
                local.upstream = upstream
            logger.info("%s: created branch %s tracking %s/%s", self, name, remote, name)
        elif local.peel(Commit).id != tip:
            local.set_target(tip, f"gittool: fast-forward {name} to {remote}/{name}")
            local = self._repo.branches.local[name]
            logger.info("%s: fast-forwarded %s to %s/%s", self, name, remote, name)
        self._repo.checkout(local)
        self.update_submodules()
        logger.info("%s: now on branch %s at %s", self, name, str(tip)[:10])

    def fetch(self, remote: str = "origin") -> bool:
        """`git fetch -j 8 <remote>`."""
        return self._fetch(remote)

    def fetch_with_submodules(self, remote: str = "origin") -> bool:
        """Fetch this repo and every checked-out submodule in one go, 8 at a time."""
        return self._fetch("--recurse-submodules=yes", remote)

    def _fetch(self, *args: str) -> bool:
        """`git fetch -j 8` via the CLI, so ssh agents/credential helpers just work."""
        logger.debug("%s: git fetch -j %d %s", self, FETCH_JOBS, " ".join(args))
        try:
            self._git("fetch", "--quiet", "-j", str(FETCH_JOBS), *args)
            return True
        except subprocess.CalledProcessError as exc:
            logger.warning("%s: fetch %s failed: %s", self, " ".join(args), exc.stderr.strip())
            return False

    def push(self, branch: str, remote: str = "origin") -> None:
        """`git push -u <remote> <branch>` via the CLI (uses the user's ssh/credential setup)."""
        logger.info("%s: pushing %s to %s", self, branch, remote)
        try:
            self._git("push", "-u", remote, branch)
        except subprocess.CalledProcessError as exc:
            raise RuntimeError(f"{self}: push of {branch} failed: {exc.stderr.strip()}") from exc

    def conflicted_paths(self) -> list[str]:
        return sorted({e.path for entry in self.conflicts() for e in entry if e is not None})
