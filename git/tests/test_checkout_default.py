from __future__ import annotations

import json
from pathlib import Path

from helper import BigRepo

from conftest import Workspace, branch_of, commit, git, head, upstream_of


def big(ws: Workspace) -> BigRepo:
    return BigRepo(ws.main)


def repos_json(tmp_path: Path, default: str) -> Path:
    path = tmp_path / "repos.json"
    path.write_text(json.dumps({"items": [{"path": "libs/sub", "default_branch": default,
                                           "branch_name_in_env": "SUB_BRANCH"}]}))
    return path


def test_detached_revision_contained_in_default_checks_out_its_tip(ws: Workspace, tmp_path: Path):
    old = head(ws.sub)
    git(ws.sub, "checkout", "-q", "--detach")
    git(ws.sub, "branch", "-q", "-D", "master")
    tip = ws.publish_sub_branch("develop", "d.txt", "d\n")

    assert big(ws).checkout_default(repos_json(tmp_path, "develop")) is True

    assert branch_of(ws.sub) == "develop" and head(ws.sub) == tip != old
    assert upstream_of(ws.sub, "develop") == "origin/develop"
    assert "libs/sub" in git(ws.main, "status", "--porcelain")  # pointer moved, not committed


def test_unmerged_work_stays_put(ws: Workspace, tmp_path: Path):
    git(ws.sub, "checkout", "-q", "-b", "feature")
    sha = commit(ws.sub, "f.txt", "f\n")

    assert big(ws).checkout_default(repos_json(tmp_path, "master")) is True

    assert branch_of(ws.sub) == "feature" and head(ws.sub) == sha


def test_squash_merged_work_counts_as_on_default(ws: Workspace, tmp_path: Path):
    git(ws.sub, "checkout", "-q", "-b", "feature")
    commit(ws.sub, "f.txt", "f\n")
    commit(ws.sub, "f.txt", "f2\n")
    git(ws.sub, "push", "-q", "-u", "origin", "feature")
    git(ws.sub_dev, "fetch", "-q")
    git(ws.sub_dev, "merge", "-q", "--squash", "origin/feature")
    git(ws.sub_dev, "commit", "-q", "-m", "squash feature")
    git(ws.sub_dev, "push", "-q", "origin", "master")
    squashed = head(ws.sub_dev)

    assert big(ws).checkout_default(repos_json(tmp_path, "master")) is True

    assert branch_of(ws.sub) == "master" and head(ws.sub) == squashed


def test_behind_local_default_is_fast_forwarded(ws: Workspace):
    tip = ws.publish_sub_branch("master", "m.txt", "m\n")
    git(ws.sub, "checkout", "-q", "--detach")

    # no repos.json: falls back to origin/HEAD / master
    assert big(ws).checkout_default() is True

    assert branch_of(ws.sub) == "master" and head(ws.sub) == tip


def test_dirty_submodule_and_dry_run_are_left_alone(ws: Workspace, tmp_path: Path):
    git(ws.sub, "checkout", "-q", "--detach")
    detached = head(ws.sub)
    repos = repos_json(tmp_path, "master")

    assert big(ws).checkout_default(repos, dry_run=True) is True
    assert branch_of(ws.sub) == "HEAD"

    (ws.sub / "sub.txt").write_text("dirty\n")
    assert big(ws).checkout_default(repos) is True
    assert branch_of(ws.sub) == "HEAD" and head(ws.sub) == detached


def test_missing_default_branch_fails(ws: Workspace, tmp_path: Path):
    assert big(ws).checkout_default(repos_json(tmp_path, "nope")) is False
