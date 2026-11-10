"""A main repository together with its submodules."""

from __future__ import annotations

import json
import re
from pathlib import Path

from pygit2 import GitError, Oid
from pygit2.enums import FileMode

from . import ai, github
from .log import logger
from .repo import GitRepo
from .utils import Chooser, console_chooser

# `CORE_BRANCH=master` style lines in PR templates: which branch of a dependency CI builds with.
TEMPLATE_BRANCH_LINE = re.compile(
    r"^(?P<indent>[ \t]*)(?P<key>[A-Za-z0-9_]+)_BRANCH=(?P<value>[^\r\n]*?)(?P<cr>\r?)$", re.MULTILINE)
# The CI parameters block of a template: optional "**Parameters**" line, then a fence
# holding PR_START_ENV ... PR_END_ENV.
PARAMS_BLOCK = re.compile(r"(?:^\*\*Parameters\*\*[ \t]*\r?\n)?^```[^\n]*\n[^`]*?PR_END_ENV=[^\n]*\n```",
                          re.MULTILINE)
# Maps CI env keys to submodule paths: {"items": [{"path", "default_branch", "branch_name_in_env"}]}.
REPOS_JSON = Path("buildPlugin") / "root" / "repos.json"


def _norm(name: str) -> str:
    """'BUILD_PLUGIN', 'buildPlugin', 'build-plugin' -> 'buildplugin'."""
    return re.sub(r"[^a-z0-9]", "", name.lower())


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
        """Merge `branch` into the main repo, submodules first.

        Every submodule whose pointer differs between HEAD and `branch` is checked
        before anything is touched: it must be on a branch, be clean, and merging
        the commit `branch` records for it into that branch must not conflict. Any
        failure aborts the whole merge with nothing changed. Then each submodule
        gets that commit merged in (fast-forward or merge commit), and finally the
        main repo is merged as usual, recording the merged submodule commits. File
        conflicts in the main repo go to the AI tool if one is configured.
        Returns True when everything is committed."""
        target = self._repo.branch_tip(branch)
        self._repo.ensure_can_merge()

        plan, problems = self._check_submodules(branch, target)
        if problems:
            logger.error("Not merging %s, submodules are not safe to merge:\n  %s",
                         branch, "\n  ".join(problems))
            return False

        pinned: dict[str, Oid] = {}
        for path, sub, theirs in plan:
            into = sub.current_branch
            logger.info("Submodule %s: merging %s (recorded on %s) into %s",
                        path, str(theirs)[:10], branch, into)
            if not sub.merge_commit(theirs, f"Merge {branch}'s {path} ({str(theirs)[:10]}) into {into}"):
                # checked conflict-free just above, so only a race gets here
                raise RuntimeError(f"Submodule {path}: unexpected conflicts merging {str(theirs)[:10]}; "
                                   f"fix them in {sub.workdir}")
            pinned[path] = sub.head_id

        into = self.main_branch or "detached HEAD"
        if not self._repo.merge_commit(target, f"Merge branch '{branch}' into {into}", pinned):
            logger.warning("Merge of %s stopped on conflicts", branch)
            return self.resolve_conflicts()
        return True

    def _check_submodules(self, branch: str, target: Oid) -> tuple[list[tuple[str, GitRepo, Oid]], list[str]]:
        """Returns (submodules to merge as (path, repo, their commit), problems)."""
        plan: list[tuple[str, GitRepo, Oid]] = []
        problems: list[str] = []
        head = self._repo.head_id
        for module in self._repo.submodules:
            path = module.path
            ours = self._repo.gitlink(head, path)
            theirs = self._repo.gitlink(target, path)
            if ours is None or theirs is None or ours == theirs:
                continue  # added/removed on one side, or untouched: the main merge handles it
            try:
                sub = GitRepo.from_submodule(module)
            except GitError:
                problems.append(f"{path}: not initialised (run `gittool sync`)")
                continue
            if sub.current_branch is None:
                problems.append(f"{path}: detached at {str(sub.head_id)[:10]}, not on a branch "
                                "(run `gittool sync` or check one out)")
                continue
            dirty = sub.changed_paths()
            if dirty:
                problems.append(f"{path}: uncommitted changes: {', '.join(dirty)}")
                continue
            if not sub.has_commit(theirs):
                sub.fetch_all()
            if not sub.has_commit(theirs):
                problems.append(f"{path}: commit {str(theirs)[:10]} recorded on {branch} is not "
                                "available, even after fetching")
                continue
            if sub.contains(sub.head_id, theirs):
                logger.info("Submodule %s: %s already contains %s", path, sub.current_branch,
                            str(theirs)[:10])
                continue
            conflicts = sub.merge_conflicts_with(theirs)
            if conflicts:
                problems.append(f"{path}: merging {str(theirs)[:10]} (recorded on {branch}) into "
                                f"{sub.current_branch} conflicts in {', '.join(conflicts)}")
                continue
            plan.append((path, sub, theirs))
        return plan, problems

    def resolve_conflicts(self) -> bool:
        """Finish a main-repo merge left on conflicts: hand leftover files to the AI
        tool if configured, then commit. Safe to re-run."""
        if self._repo.conflicts():
            return self._resolve_main_conflicts()
        if self._repo.merge_in_progress():
            logger.info("No conflicts left, committing the merge")
            self._repo.finish_merge()
        return True

    def _resolve_main_conflicts(self) -> bool:
        ours = self.main_branch or "HEAD"
        theirs = self._repo.merge_source() or "MERGE_HEAD"
        submodules = {module.path: module for module in self._repo.submodules}
        files: list[str] = []
        stuck: list[str] = []

        for ancestor, our_entry, their_entry in self._repo.conflicts():
            path = next(e.path for e in (ancestor, our_entry, their_entry) if e is not None)
            if path not in submodules:
                files.append(path)
            elif not self._take_merged_submodule(path, submodules[path], our_entry, their_entry):
                stuck.append(path)

        if stuck:
            logger.error("Submodule pointer conflicts in %s: the submodule checkout does not contain "
                         "both sides. Merge them inside the submodule, `git add` it, then run "
                         "`gittool resolve_conflicts` again.", ", ".join(stuck))
        if files:
            files = self._resolve_with_ai(self._repo, files, ours, theirs, list(submodules))
        if files:
            logger.error("Still conflicted: %s. Resolve by hand and `git add`, then run "
                         "`gittool resolve_conflicts` again.", ", ".join(files))
        if stuck or files:
            return False
        self._repo.finish_merge()
        self._repo.update_submodules()
        return True

    def _take_merged_submodule(self, path: str, module, our_entry, their_entry) -> bool:
        """Stage the submodule checkout's commit when it contains both sides (e.g. a
        merge started by plain `git merge` after merging the submodule by hand)."""
        try:
            sub = GitRepo.from_submodule(module)
        except GitError:
            return False
        head = sub.head_id
        if all(entry is None or (sub.has_commit(entry.id) and sub.contains(head, entry.id))
               for entry in (our_entry, their_entry)):
            self._repo.stage_blob(path, head, FileMode.COMMIT)
            logger.info("Submodule %s: recording its checkout %s, which has both sides", path,
                        str(head)[:10])
            return True
        return False

    # --------------------------------------------------------------- ai ---

    def _resolve_with_ai(self, repo: GitRepo, files: list[str], ours: str, theirs: str,
                         submodules: list[str]) -> list[str]:
        """Offer/launch the AI tool for `files`; return the paths still conflicted."""
        tool = self._pick_ai_tool()
        if tool is None:
            return files
        prompt = ai.conflict_prompt(repo.workdir, ours, theirs, files, submodules)
        ai.run_tool(tool, prompt, repo.workdir)
        left = [path for path in repo.conflicted_paths() if path not in submodules]
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

    # ------------------------------------------------------- create_prs ---

    def create_prs(self, base: str | None = None, push: bool = False, draft: bool = False,
                   dry_run: bool = False, include_main: bool = False,
                   title: str | None = None, repos_json: Path | None = None,
                   edit: bool = True) -> bool:
        """Open a PR into the default branch for every submodule whose current
        branch is not merged into it yet. A branch counts as merged when the
        default branch contains its HEAD, or a merged PR has exactly that HEAD
        (squash merges). Branches with an open PR are reported, not duplicated.
        The PR body is the repo's PR template (empty if it has none) with each
        `<DEP>_BRANCH=` line set to that dependency submodule's current branch (see
        `_dependency_branches`). With `edit`, an already open PR whose body has wrong
        `<KEY>_BRANCH=` values (or no parameters block) is corrected; the title is
        `title`, else the commit subject for a single-commit branch, else the branch name.
        Returns False when some repo needed a PR and did not get one."""
        github.ensure_available()
        targets: list[tuple[str, GitRepo, str | None]] = [
            (module.path, GitRepo.from_submodule(module), module.branch)
            for module in self._repo.submodules]
        if include_main:
            targets.append((".", self._repo, None))
        self._repo.fetch_with_submodules()

        dep_branches = self._dependency_branches(targets, repos_json)

        ok = True
        summary: list[str] = []
        for path, repo, configured in targets:
            outcome, good = self._create_pr(path, repo, configured, base, push, draft, dry_run, title,
                                            dep_branches, edit)
            summary.append(f"{path}: {outcome}")
            ok &= good
        logger.info("PR summary:\n  %s", "\n  ".join(summary))
        return ok

    def _create_pr(self, path: str, repo: GitRepo, configured: str | None, base: str | None,
                   push: bool, draft: bool, dry_run: bool, title: str | None,
                   dep_branches: dict[str, str | None], edit: bool) -> tuple[str, bool]:
        """Returns (one-line outcome, ok)."""
        branch = repo.current_branch
        if branch is None:
            logger.warning("Submodule %s: detached HEAD, skipping (run `gittool sync` first)", path)
            return "skipped, detached HEAD", True
        target = base or repo.default_branch(configured)
        if target is None:
            logger.error("Submodule %s: cannot tell the default branch; pass --base", path)
            return "failed, unknown default branch", False
        if branch == target:
            return f"skipped, on {target} itself", True
        target_tip = repo.remote_tip(target)
        if target_tip is None:
            logger.error("Submodule %s: origin/%s does not exist", path, target)
            return f"failed, no origin/{target}", False

        head = repo.head_id
        if repo.contains(target_tip, head):
            logger.info("Submodule %s: %s is already merged into %s", path, branch, target)
            return f"merged into {target}", True

        open_prs = github.find_prs(repo.workdir, branch, "open")
        if open_prs:
            pr = open_prs[0]
            logger.info("Submodule %s: PR already open for %s: %s", path, branch, pr["url"])
            if not edit:
                return f"PR already open {pr['url']}", True
            return self._fix_open_pr(path, repo, pr, dep_branches, dry_run)
        merged = [pr for pr in github.find_prs(repo.workdir, branch, "merged")
                  if pr.get("headRefOid") == str(head)]
        if merged:
            logger.info("Submodule %s: %s was merged via %s", path, branch, merged[0]["url"])
            return f"merged via {merged[0]['url']}", True

        remote_head = repo.remote_tip(branch)
        if remote_head != head:
            if remote_head is not None and not repo.contains(head, remote_head):
                logger.error("Submodule %s: %s and origin/%s have diverged; fix that first",
                             path, branch, branch)
                return f"failed, diverged from origin/{branch}", False
            if not push:
                logger.error("Submodule %s: %s has commits not pushed to origin; push it or pass "
                             "--push", path, branch)
                return "failed, not pushed (use --push)", False
            if not dry_run:
                repo.push(branch)

        pr_title = title or self._pr_title(repo, branch, target_tip)
        body, replaced = self._pr_body(path, repo, dep_branches)
        if dry_run:
            logger.info("Submodule %s: would open PR %s -> %s, title %r, branches set: %s\n%s", path,
                        branch, target, pr_title, ", ".join(replaced) or "none", body)
            return f"would open PR {branch} -> {target}: {pr_title!r}", True
        url = github.create_pr(repo.workdir, branch, target, pr_title, body, draft)
        logger.info("Submodule %s: opened PR %s -> %s: %s", path, branch, target, url)
        return f"opened {url}", True

    def _dependency_branches(self, targets: list[tuple[str, GitRepo, str | None]],
                             repos_json: Path | None) -> dict[str, str | None]:
        """Normalised env key (e.g. 'core' for CORE_BRANCH) -> the branch CI should
        build that dependency from: its submodule's current branch, or its default
        branch (repos.json `default_branch`, else origin/HEAD etc.) when it is
        detached, on the default, not on origin, or already merged into the default.
        None only when the default cannot be told (the template value is kept).

        Keys come from repos.json (`branch_name_in_env` -> `path`); submodules it
        does not list are matched by their folder/submodule name instead."""
        by_path = {path: (repo, configured) for path, repo, configured in targets if path != "."}
        keys: dict[str, tuple[str, str | None]] = {}  # norm key -> (path, default branch)
        for item in self._repos_json_items(repos_json):
            env = item.get("branch_name_in_env", "")
            if env.endswith("_BRANCH") and item.get("path") in by_path:
                keys[_norm(env[:-len("_BRANCH")])] = (item["path"], item.get("default_branch"))
        for path, (_, configured) in by_path.items():
            for name in (Path(path).name, path):
                keys.setdefault(_norm(name), (path, configured))

        result: dict[str, str | None] = {}
        for key, (path, default) in keys.items():
            repo, configured = by_path[path]
            branch = repo.current_branch
            default = default or repo.default_branch(configured)
            result[key] = default
            if branch is None or branch == default:
                continue
            tip = repo.remote_tip(branch)
            default_tip = repo.remote_tip(default) if default else None
            if tip is None:
                logger.warning("Submodule %s: %s is not on origin, PR templates use %s instead",
                               path, branch, default)
            elif default_tip is None or not repo.contains(default_tip, tip):
                result[key] = branch  # unmerged work CI must build against
        return result

    @staticmethod
    def _pr_body(path: str, repo: GitRepo, dep_branches: dict[str, str | None]) -> tuple[str, list[str]]:
        """The repo's PR template (or ""), with every `<DEP>_BRANCH=` line set to the
        dependency's branch from `dep_branches` when it has one.
        Returns (body, ["CORE_BRANCH=feature", ...] that were changed)."""
        template = github.find_template(repo.workdir)
        if template is None:
            logger.info("Submodule %s: no PR template, leaving the body empty", path)
            return "", []
        replaced: list[str] = []

        def substitute(match: re.Match) -> str:
            key = match["key"]
            if _norm(key) not in dep_branches:
                logger.warning("Submodule %s: template key %s_BRANCH matches no submodule; kept",
                               path, key)
                return match[0]
            branch = dep_branches[_norm(key)]
            if branch is None or branch == match["value"].strip():
                return match[0]
            replaced.append(f"{key}_BRANCH={branch}")
            return f"{match['indent']}{key}_BRANCH={branch}{match['cr']}"

        return TEMPLATE_BRANCH_LINE.sub(substitute, template.read_text()), replaced

    def _fix_open_pr(self, path: str, repo: GitRepo, pr: dict, dep_branches: dict[str, str | None],
                     dry_run: bool) -> tuple[str, bool]:
        generated, _ = self._pr_body(path, repo, dep_branches)
        current = pr.get("body") or ""
        fixed = self._corrected_body(current, generated, dep_branches)
        if fixed == current:
            return f"PR already open {pr['url']} (body ok)", True
        if dry_run:
            logger.info("Submodule %s: would update the body of %s to:\n%s", path, pr["url"], fixed)
            return f"PR already open {pr['url']} (would update body)", True
        github.edit_pr_body(repo.workdir, pr["number"], fixed)
        logger.info("Submodule %s: updated the body of %s", path, pr["url"])
        return f"PR already open {pr['url']} (body updated)", True

    @staticmethod
    def _corrected_body(current: str, generated: str, dep_branches: dict[str, str | None]) -> str:
        """`current` with its `<KEY>_BRANCH=` lines set to what `generated` (the
        filled template) says; free text is kept. A body without a PR_START_ENV
        block gets the generated parameters block appended."""
        if not generated:
            return current
        wanted = {_norm(m["key"]): m["value"] for m in TEMPLATE_BRANCH_LINE.finditer(generated)}
        if "PR_START_ENV=" not in current:
            block = PARAMS_BLOCK.search(generated)
            extra = block[0] if block else generated
            return f"{current.rstrip()}\n\n{extra}\n" if current.strip() else generated

        def substitute(match: re.Match) -> str:
            key = _norm(match["key"])
            value = wanted.get(key)
            if value is None and dep_branches.get(key):
                value = dep_branches[key]  # key the template lacks but the body has
            if value is None or value == match["value"]:
                return match[0]
            return f"{match['indent']}{match['key']}_BRANCH={value}{match['cr']}"

        return TEMPLATE_BRANCH_LINE.sub(substitute, current)

    @staticmethod
    def _pr_title(repo: GitRepo, branch: str, target_tip: Oid) -> str:
        commits = repo.commits_since(target_tip)
        if len(commits) == 1:
            return commits[0].message.splitlines()[0].strip() or branch
        return branch

    def _repos_json_items(self, repos_json: Path | None) -> list[dict]:
        """`items` of `repos_json`, else of buildPlugin/root/repos.json when present."""
        json_path = repos_json or (self._repo.workdir / REPOS_JSON)
        if json_path.is_file():
            return json.loads(json_path.read_text()).get("items", [])
        if repos_json is not None:
            raise ValueError(f"{repos_json} does not exist")
        return []

    # ------------------------------------------------- checkout_default ---

    def checkout_default(self, repos_json: Path | None = None, fetch: bool = True,
                         dry_run: bool = False) -> bool:
        """Put every submodule on its default branch (repos.json `default_branch`,
        else origin/HEAD, the .gitmodules branch, main/master), but only when that
        branch already has the code of the submodule's current revision: HEAD is
        reachable from it, or merging HEAD into it would change nothing (squash
        merges). Submodules with local changes, or whose work is not on the
        default branch yet, are left alone. The main repo is not committed: the
        moved submodule pointers show up as changes there.
        Returns False when a submodule could not tell or reach its default branch."""
        defaults = {item["path"]: item["default_branch"] for item in self._repos_json_items(repos_json)
                    if item.get("path") and item.get("default_branch")}
        if fetch:
            self._repo.fetch_with_submodules()
        ok = True
        summary: list[str] = []
        for module in self._repo.submodules:
            path = module.path
            repo = GitRepo.from_submodule(module)
            outcome, good = self._checkout_default(path, repo, defaults.get(path) or
                                                   repo.default_branch(module.branch), dry_run)
            summary.append(f"{path}: {outcome}")
            ok &= good
        logger.info("checkout_default summary:\n  %s", "\n  ".join(summary) or "no submodules")
        return ok

    @staticmethod
    def _checkout_default(path: str, repo: GitRepo, default: str | None,
                          dry_run: bool) -> tuple[str, bool]:
        """Returns (one-line outcome, ok)."""
        if default is None:
            logger.error("Submodule %s: cannot tell the default branch; add it to repos.json", path)
            return "failed, unknown default branch", False
        tip = repo.branch_checkout_tip(default)
        if tip is None:
            logger.error("Submodule %s: branch %s exists neither locally nor on origin", path, default)
            return f"failed, no branch {default}", False
        head = repo.head_id
        if repo.current_branch == default and tip == head:
            return f"already on {default}", True
        dirty = repo.changed_paths()
        if dirty:
            logger.warning("Submodule %s: uncommitted changes, staying put: %s", path, ", ".join(dirty))
            return "skipped, uncommitted changes", True
        where = repo.current_branch or f"detached {str(head)[:10]}"
        if not repo.has_changes_of(tip, head):
            logger.warning("Submodule %s: %s has code that %s lacks, staying on it", path, where, default)
            return f"skipped, {where} not merged into {default}", True
        if dry_run:
            return f"would check out {default} ({str(tip)[:10]}) from {where}", True
        repo.checkout_branch(default)
        return f"checked out {default} ({str(tip)[:10]}) from {where}", True

    # ---------------------------------------------------------- remove ---

    def remove_submodules(self) -> None:
        """Deinit, unstage and delete every submodule (including .git/modules)."""
        self._repo.remove_all_submodules()
