"""A main repository together with its submodules."""

from __future__ import annotations

import json
from pathlib import Path

from pygit2 import Oid

from . import ai
from .log import logger
from .repo import GitRepo
from .utils import Chooser, console_chooser

# Submodule merges deferred until the main merge is committed, keyed by submodule
# path. Lives in .git/ so a later `resolve_conflicts` run can pick them up.
PENDING_FILE = "gittool-pending-submodules.json"


class BigRepo:

    def __init__(self, path: str | Path, chooser: Chooser | None = None, ai: str | None = None) -> None:
        """`ai`: None = never use an AI tool, "ask" = offer the installed ones when
        conflicts remain, or a tool name (claude, agy, or one from GITTOOL_AI_TOOLS)."""
        self._repo = GitRepo.open(path)
        self._chooser: Chooser = chooser or console_chooser
        self._ai = ai

    @property
    def main_branch(self) -> str | None:
        return self._repo.current_branch

    def _submodule_repos(self) -> list[tuple[str, GitRepo]]:
        return [(module.path, GitRepo.from_submodule(module)) for module in self._repo.submodules]

    # ------------------------------------------------------------- sync ---

    def sync_branch(self) -> bool:
        """Init/update every submodule, then put each detached submodule on the
        branch matching the main repo's branch (or the only/chosen candidate).
        Returns True when every submodule ends up on a branch."""
        ok = self._repo.update_submodules()
        main_branch = self.main_branch
        if main_branch is None:
            logger.warning("Main repo is detached; submodules will be matched by candidate branch only")
        for path, repo in self._submodule_repos():
            if not repo.is_detached:
                logger.info("Submodule %s: on branch %s", path, repo.current_branch)
                continue
            ok &= repo.attach_head_to_branch(main_branch, self._chooser)
        return ok

    # ---------------------------------------------------------- verify ---

    def verify_before_push(self) -> bool:
        """Every submodule must be clean and its HEAD reachable from a remote
        branch, and the main repo must be clean. Otherwise pushing the main repo
        publishes submodule pointers nobody else can fetch."""
        problems = 0
        for path, repo in self._submodule_repos():
            dirty = repo.changed_paths()
            if dirty:
                logger.error("Submodule %s has uncommitted changes: %s", path, ", ".join(dirty))
                problems += 1
            if not repo.head_is_on_remote():
                logger.error("Submodule %s: commit %s is not on any remote branch; push it first",
                             path, str(repo.head_id)[:10])
                problems += 1
        dirty = self._repo.changed_paths()
        if dirty:
            logger.error("Main repo has uncommitted changes: %s", ", ".join(dirty))
            problems += 1

        if problems:
            logger.error("Not ready to push: %d problem(s)", problems)
            return False
        logger.info("All repos are ready to push")
        return True

    # ----------------------------------------------------------- merge ---

    def merge(self, branch: str) -> bool:
        """Merge `branch` into the main repo. Conflicting submodule pointers keep
        our side so the merge commits quickly; each such submodule then gets
        their matching branch merged into ours in a follow-up commit. File
        conflicts go to the AI tool if one is configured. Returns True when
        everything is committed."""
        if not self._repo.merge_branch(branch):
            logger.warning("Merge of %s stopped on conflicts", branch)
        return self.resolve_conflicts()

    def resolve_conflicts(self) -> bool:
        """Finish whatever merge work is outstanding: main-repo conflicts, the
        merge commit, then deferred submodule merges. Safe to re-run."""
        if self._repo.conflicts():
            if not self._resolve_main_conflicts():
                return False
        elif self._repo.merge_in_progress():
            logger.info("No conflicts left, committing the merge")
            self._repo.finish_merge()
        return self._merge_pending_submodules()

    def _resolve_main_conflicts(self) -> bool:
        ours = self.main_branch or "HEAD"
        theirs = self._repo.merge_source() or "MERGE_HEAD"
        submodules = {module.path: module for module in self._repo.submodules}
        pending = self._load_pending()
        remaining: list[str] = []

        for ancestor, our_entry, their_entry in self._repo.conflicts():
            path = next(e.path for e in (ancestor, our_entry, their_entry) if e is not None)
            if path in submodules and our_entry is not None and their_entry is not None:
                self._repo.stage_blob(path, our_entry.id, our_entry.mode)
                pending[path] = {"theirs": str(their_entry.id), "their_branch": theirs, "our_branch": ours}
                logger.info("Submodule %s: keeping our commit %s for the merge; '%s' will be merged "
                            "into it afterwards", path, str(our_entry.id)[:10], theirs)
            else:
                remaining.append(path)
        self._save_pending(pending)

        if remaining:
            remaining = self._resolve_with_ai(self._repo, remaining, ours, theirs, list(submodules))
        if remaining:
            logger.error("Still conflicted: %s. Resolve by hand and `git add`, then run "
                         "`gittool resolve_conflicts` again.", ", ".join(remaining))
            return False
        self._repo.finish_merge()
        return True

    # ------------------------------------------------ deferred submodules ---

    def _merge_pending_submodules(self) -> bool:
        pending = self._load_pending()
        if not pending:
            return True
        if self._repo.merge_in_progress():
            return False
        submodules = {module.path: module for module in self._repo.submodules}
        for path, info in list(pending.items()):
            module = submodules.get(path)
            if module is None:
                logger.warning("Submodule %s no longer exists; dropping its pending merge", path)
                del pending[path]
                self._save_pending(pending)
                continue
            sub = GitRepo.from_submodule(module)
            if not self._merge_into_submodule(path, sub, info):
                return False
            if self._repo.staged_id(path) != sub.head_id:
                self._repo.stage(path)
                self._repo.commit_index(
                    f"Update submodule {path}: merge '{info['their_branch']}' into "
                    f"{sub.current_branch or 'detached HEAD'}")
            del pending[path]
            self._save_pending(pending)
        return True

    def _merge_into_submodule(self, path: str, sub: GitRepo, info: dict) -> bool:
        their_branch: str = info["their_branch"]
        if sub.merge_in_progress():  # resuming after a manual or AI round
            left = sub.conflicted_paths()
            if left:
                left = self._resolve_with_ai(sub, left, sub.current_branch or "HEAD", their_branch, [])
            if left:
                logger.error("Submodule %s still conflicted: %s", path, ", ".join(left))
                return False
            sub.finish_merge()
            return True

        dirty = sub.changed_paths()
        if dirty:
            logger.error("Submodule %s has uncommitted changes, not merging: %s", path, ", ".join(dirty))
            return False
        sub.fetch_all()
        if sub.is_detached and not sub.attach_head_to_branch(info["our_branch"], self._chooser):
            logger.warning("Submodule %s: merging on a detached HEAD; put the result on a branch", path)

        target = sub.resolve_branch_tip(their_branch)
        label = their_branch
        if target is None:
            target = Oid(hex=info["theirs"])
            label = str(target)[:10]
            logger.warning("Submodule %s: no branch named '%s'; merging the recorded commit %s instead",
                           path, their_branch, label)
        if not sub.has_commit(target):
            logger.error("Submodule %s: commit %s is not available locally", path, str(target)[:10])
            return False

        into = sub.current_branch or "detached HEAD"
        logger.info("Submodule %s: merging '%s' into %s", path, label, into)
        if sub.merge_commit(target, f"Merge branch '{label}' into {into}"):
            return True
        left = self._resolve_with_ai(sub, sub.conflicted_paths(), into, label, [])
        if left:
            logger.error("Submodule %s still conflicted: %s. Fix it in %s, `git add`, then run "
                         "`gittool resolve_conflicts` again.", path, ", ".join(left), sub.workdir)
            return False
        sub.finish_merge()
        return True

    # --------------------------------------------------------------- ai ---

    def _resolve_with_ai(self, repo: GitRepo, files: list[str], ours: str, theirs: str,
                         submodules: list[str]) -> list[str]:
        """Offer/launch the AI tool for `files`; return the paths still conflicted."""
        tool = self._pick_ai_tool()
        if tool is None:
            return files
        prompt = ai.conflict_prompt(repo.workdir, ours, theirs, files, submodules)
        ai.run_tool(tool, prompt, repo.workdir)
        left = repo.conflicted_paths()
        if left:
            logger.warning("%s left conflicts in %s", tool, ", ".join(left))
        return left

    def _pick_ai_tool(self) -> str | None:
        if self._ai is None:
            return None
        if self._ai != "ask":
            ai.tool_command(self._ai, "")  # raises ValueError for unknown names
            return self._ai
        tools = ai.available_tools()
        if not tools:
            logger.info("No AI tool installed (%s); resolve by hand", ", ".join(ai.known_tools()))
            return None
        index = self._chooser("Conflicts remain. Resolve them with an AI tool?", tools)
        return tools[index] if index is not None else None

    # ---------------------------------------------------------- pending ---

    def _pending_path(self) -> Path:
        return self._repo.gitdir / PENDING_FILE

    def _load_pending(self) -> dict[str, dict]:
        path = self._pending_path()
        return json.loads(path.read_text()) if path.exists() else {}

    def _save_pending(self, pending: dict[str, dict]) -> None:
        path = self._pending_path()
        if pending:
            path.write_text(json.dumps(pending, indent=2) + "\n")
        elif path.exists():
            path.unlink()

    # ---------------------------------------------------------- remove ---

    def remove_submodules(self) -> None:
        """Deinit, unstage and delete every submodule (including .git/modules)."""
        self._repo.remove_all_submodules()
