"""Fixtures that build a realistic main-repo + submodule workspace with the git CLI.

Layout under tmp_path:
    remote/main.git   bare "server" copy of the main repo
    remote/sub.git    bare "server" copy of the submodule
    sub_dev/          an independent checkout of sub.git used to publish commits
    main/             the developer's recursive clone of main.git (repo under test)
    main/libs/sub     the submodule inside that clone
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

GIT_OVERRIDES = {
    "GIT_AUTHOR_NAME": "Test",
    "GIT_AUTHOR_EMAIL": "test@example.com",
    "GIT_COMMITTER_NAME": "Test",
    "GIT_COMMITTER_EMAIL": "test@example.com",
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_CONFIG_SYSTEM": "/dev/null",
}


def cli_env(**extra: str) -> dict[str, str]:
    """Current environment (so monkeypatched PATH/GITTOOL_* apply) plus a fixed git identity."""
    return {**os.environ, **GIT_OVERRIDES, **extra}


def git(cwd: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-c", "protocol.file.allow=always", "-c", "init.defaultBranch=master", *args],
        cwd=cwd,
        env=cli_env(),
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def commit(repo: Path, filename: str, content: str, message: str | None = None) -> str:
    (repo / filename).write_text(content)
    git(repo, "add", filename)
    git(repo, "commit", "-q", "-m", message or f"{filename}: {content.strip()}")
    return head(repo)


def head(repo: Path) -> str:
    return git(repo, "rev-parse", "HEAD")


def branch_of(repo: Path) -> str:
    """Current branch name, or 'HEAD' when detached."""
    return git(repo, "rev-parse", "--abbrev-ref", "HEAD")


def upstream_of(repo: Path, branch: str) -> str | None:
    try:
        return git(repo, "rev-parse", "--abbrev-ref", f"{branch}@{{upstream}}")
    except subprocess.CalledProcessError:
        return None


def parents_of(repo: Path, rev: str = "HEAD") -> list[str]:
    return git(repo, "rev-list", "--parents", "-n", "1", rev).split()[1:]


def set_identity(repo: Path) -> None:
    """pygit2 reads user.name/email from the repo config (it ignores GIT_* env)."""
    git(repo, "config", "user.name", "Test")
    git(repo, "config", "user.email", "test@example.com")


@dataclass
class Workspace:
    root: Path
    remote_main: Path
    remote_sub: Path
    sub_dev: Path
    main: Path
    sub: Path

    def publish_sub_branch(self, branch: str, filename: str, content: str, start: str = "master") -> str:
        """Create `branch` in the submodule from `start`, add one commit, push it. Returns the sha."""
        git(self.sub_dev, "checkout", "-q", "-B", branch, start)
        sha = commit(self.sub_dev, filename, content)
        git(self.sub_dev, "push", "-q", "-u", "origin", branch)
        return sha

    def point_sub_at(self, sha: str) -> None:
        """Detach the submodule checkout at `sha` and stage that in the main repo."""
        git(self.sub, "fetch", "-q", "origin")
        git(self.sub, "checkout", "-q", "--detach", sha)
        git(self.main, "add", "libs/sub")


FAKE_AI_RESOLVE = """#!/bin/sh
# Pretend to be an AI coding tool: record the prompt, resolve every conflicted
# file in cwd with a fixed body and stage it. Never commits.
printf '%s' "$*" > "$FAKE_AI_PROMPT_LOG"
for f in $(git diff --name-only --diff-filter=U); do
    printf 'resolved by ai\\n' > "$f"
    git add -- "$f"
done
"""

FAKE_AI_NOOP = """#!/bin/sh
printf '%s' "$*" > "$FAKE_AI_PROMPT_LOG"
"""


@pytest.fixture
def fake_ai(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Install an executable named `fake-ai` on PATH and make gittool run AI
    tools inline (no terminal window). Returns a function giving the prompt log
    path; call it with resolve=False for a tool that fixes nothing."""
    bin_dir = tmp_path / "fake-bin"
    bin_dir.mkdir()
    log = tmp_path / "fake-ai-prompt.txt"
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("GITTOOL_TERMINAL", "inline")
    monkeypatch.setenv("GITTOOL_AI_TOOLS", "fake-ai")
    monkeypatch.setenv("FAKE_AI_PROMPT_LOG", str(log))

    def install(resolve: bool = True) -> Path:
        script = bin_dir / "fake-ai"
        script.write_text(FAKE_AI_RESOLVE if resolve else FAKE_AI_NOOP)
        script.chmod(0o755)
        return log

    return install


@pytest.fixture
def ws(tmp_path: Path) -> Workspace:
    remote = tmp_path / "remote"
    remote.mkdir()
    remote_main = remote / "main.git"
    remote_sub = remote / "sub.git"
    git(remote, "init", "-q", "--bare", str(remote_main))
    git(remote, "init", "-q", "--bare", str(remote_sub))

    sub_dev = tmp_path / "sub_dev"
    git(tmp_path, "clone", "-q", str(remote_sub), str(sub_dev))
    commit(sub_dev, "sub.txt", "v1\n", "sub: initial")
    git(sub_dev, "push", "-q", "-u", "origin", "master")

    main_dev = tmp_path / "main_dev"
    git(tmp_path, "clone", "-q", str(remote_main), str(main_dev))
    commit(main_dev, "main.txt", "v1\n", "main: initial")
    git(main_dev, "submodule", "add", "-q", str(remote_sub), "libs/sub")
    git(main_dev, "commit", "-q", "-m", "main: add submodule")
    git(main_dev, "push", "-q", "-u", "origin", "master")

    main = tmp_path / "main"
    git(tmp_path, "clone", "-q", "--recurse-submodules", str(remote_main), str(main))
    sub = main / "libs" / "sub"
    set_identity(main)
    set_identity(sub)

    return Workspace(tmp_path, remote_main, remote_sub, sub_dev, main, sub)
