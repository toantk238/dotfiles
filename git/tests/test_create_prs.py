from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from helper import BigRepo

from conftest import Workspace, commit, git, head

FAKE_GH = """#!/bin/sh
# Fake GitHub CLI: log every call; `pr list --state S` answers $FAKE_GH_DIR/S.json
# (default []); `pr create` prints a URL.
for a in "$@"; do printf '[%s]' "$a"; done >> "$FAKE_GH_DIR/calls.log"; echo >> "$FAKE_GH_DIR/calls.log"
if [ "$1 $2" = "pr list" ]; then
    state=""
    while [ $# -gt 0 ]; do [ "$1" = "--state" ] && state="$2"; shift; done
    cat "$FAKE_GH_DIR/$state.json" 2>/dev/null || echo '[]'
elif [ "$1 $2" = "pr create" ]; then
    echo "https://github.com/acme/sub/pull/7"
fi
"""


class FakeGh:
    def __init__(self, root: Path) -> None:
        self.root = root

    def calls(self) -> list[str]:
        log = self.root / "calls.log"
        return log.read_text().splitlines() if log.exists() else []

    def creates(self) -> list[str]:
        return [c for c in self.calls() if c.startswith("[pr][create]")]

    def answer(self, state: str, prs: list[dict]) -> None:
        (self.root / f"{state}.json").write_text(json.dumps(prs))


@pytest.fixture
def gh(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> FakeGh:
    root = tmp_path / "fake-gh"
    bin_dir = root / "bin"
    bin_dir.mkdir(parents=True)
    script = bin_dir / "gh"
    script.write_text(FAKE_GH)
    script.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("FAKE_GH_DIR", str(root))
    return FakeGh(root)


def create(base: str, title: str, body: str = "") -> str:
    """The logged argv of `gh pr create` for head `feature`."""
    return f"[pr][create][--head][feature][--base][{base}][--title][{title}][--body][{body}]"


def on_feature(ws: Workspace, push: bool = True) -> str:
    """Put the submodule on a local `feature` branch one commit ahead of master."""
    git(ws.sub, "checkout", "-q", "-b", "feature")
    sha = commit(ws.sub, "f.txt", "f\n")
    if push:
        git(ws.sub, "push", "-q", "-u", "origin", "feature")
    return sha


def big(ws: Workspace) -> BigRepo:
    return BigRepo(ws.main)


def test_opens_pr_into_default_branch_for_unmerged_branch(ws: Workspace, gh: FakeGh):
    on_feature(ws)

    assert big(ws).create_prs() is True

    assert gh.creates() == [create("master", "f.txt: f")]


def test_title_is_branch_name_for_several_commits_or_the_title_option(ws: Workspace, gh: FakeGh):
    on_feature(ws)
    commit(ws.sub, "g.txt", "g\n")
    git(ws.sub, "push", "-q", "origin", "feature")

    assert big(ws).create_prs() is True
    assert big(ws).create_prs(title="My PR") is True

    assert gh.creates() == [create("master", "feature"), create("master", "My PR")]


TEMPLATE = "**Parameters**\nPR_START_ENV=1\nSUB_BRANCH=master\nOTHER_BRANCH=master\nPR_END_ENV=1\n"


def write_template(ws: Workspace) -> None:
    (ws.sub / ".github").mkdir()
    (ws.sub / ".github" / "PULL_REQUEST_TEMPLATE.md").write_text(TEMPLATE)


def created_body(gh: FakeGh) -> str:
    """Body of the single `pr create` call (the fake logs one line per argv, so read the file)."""
    text = (gh.root / "calls.log").read_text()
    start = text.index("[pr][create]")
    return text[start:].split("[--body][", 1)[1].rsplit("]", 1)[0]


def test_body_points_dependency_keys_at_the_submodules_current_branch(ws: Workspace, gh: FakeGh):
    on_feature(ws)
    write_template(ws)

    assert big(ws).create_prs() is True

    # SUB_BRANCH -> libs/sub (by folder name) is on pushed, unmerged `feature`;
    # OTHER matches no submodule, so it keeps its value
    assert created_body(gh) == TEMPLATE.replace("SUB_BRANCH=master", "SUB_BRANCH=feature")


def test_repos_json_maps_env_keys_to_submodule_paths(ws: Workspace, gh: FakeGh, tmp_path: Path):
    on_feature(ws)
    write_template(ws)
    repos = tmp_path / "repos.json"
    repos.write_text(json.dumps({"items": [{"path": "libs/sub", "default_branch": "master",
                                            "branch_name_in_env": "OTHER_BRANCH"}]}))

    assert big(ws).create_prs(repos_json=repos) is True

    assert "OTHER_BRANCH=feature" in created_body(gh)


def dependency_branches(ws: Workspace, repos_json: Path | None = None) -> dict[str, str | None]:
    sub = big(ws)._submodule_repos()[0][1]
    return big(ws)._dependency_branches([("libs/sub", sub, None)], repos_json)


def test_unpushed_or_merged_dependency_branches_fall_back_to_its_default(ws: Workspace):
    on_feature(ws)
    git(ws.sub, "push", "-q", "origin", "feature:master")  # merged
    assert dependency_branches(ws)["sub"] == "master"

    git(ws.sub, "checkout", "-q", "-b", "local-only")
    commit(ws.sub, "l.txt", "l\n")
    assert dependency_branches(ws)["sub"] == "master"


def test_dependency_on_its_default_uses_the_repos_json_default_not_the_template_value(
        ws: Workspace, gh: FakeGh, tmp_path: Path):
    # libs/sub is the "dependency" whose default is `main`; the template still says master
    git(ws.sub, "push", "-q", "origin", "master:main")
    git(ws.sub, "checkout", "-q", "-b", "main", "origin/main")
    repos = tmp_path / "repos.json"
    repos.write_text(json.dumps({"items": [{"path": "libs/sub", "default_branch": "main",
                                            "branch_name_in_env": "SUB_BRANCH"}]}))

    deps = dependency_branches(ws, repos)
    assert deps["sub"] == "main"

    write_template(ws)
    body, replaced = BigRepo._pr_body("libs/sub", big(ws)._submodule_repos()[0][1], deps)
    assert "SUB_BRANCH=main" in body and replaced == ["SUB_BRANCH=main"]


def test_skips_branch_already_merged_into_default(ws: Workspace, gh: FakeGh):
    on_feature(ws)
    git(ws.sub, "push", "-q", "origin", "feature:master")

    assert big(ws).create_prs() is True

    assert gh.calls() == []


def test_skips_submodule_on_default_branch_or_detached(ws: Workspace, gh: FakeGh):
    assert big(ws).create_prs() is True  # fresh clone: submodule is detached
    git(ws.sub, "checkout", "-q", "master")
    assert big(ws).create_prs() is True

    assert gh.calls() == []


def test_reports_existing_open_pr_instead_of_duplicating(ws: Workspace, gh: FakeGh):
    on_feature(ws)
    gh.answer("open", [{"number": 3, "url": "https://x/pull/3", "baseRefName": "master",
                        "headRefOid": "abc"}])

    assert big(ws).create_prs() is True

    assert gh.creates() == []


def test_squash_merged_pr_with_same_head_counts_as_merged(ws: Workspace, gh: FakeGh):
    sha = on_feature(ws)
    gh.answer("merged", [{"number": 2, "url": "https://x/pull/2", "baseRefName": "master",
                          "headRefOid": sha}])

    assert big(ws).create_prs() is True

    assert gh.creates() == []


def test_unpushed_branch_fails_unless_push_flag(ws: Workspace, gh: FakeGh):
    sha = on_feature(ws, push=False)

    assert big(ws).create_prs() is False
    assert gh.creates() == []

    assert big(ws).create_prs(push=True) is True
    assert git(ws.sub_dev, "ls-remote", "origin", "feature").split()[0] == sha
    assert len(gh.creates()) == 1


def test_dry_run_and_draft_and_base(ws: Workspace, gh: FakeGh):
    on_feature(ws)
    git(ws.sub, "push", "-q", "origin", "master:develop")

    assert big(ws).create_prs(dry_run=True) is True
    assert gh.creates() == []

    assert big(ws).create_prs(base="develop", draft=True) is True
    assert gh.creates() == [create("develop", "f.txt: f") + "[--draft]"]


def test_origin_head_decides_the_default_branch(ws: Workspace, gh: FakeGh):
    on_feature(ws)
    git(ws.sub, "push", "-q", "origin", "master:main")
    git(ws.sub, "remote", "set-head", "origin", "main")

    assert big(ws).create_prs() is True

    assert gh.creates() == [create("main", "f.txt: f")]


def test_include_main_handles_the_main_repo_too(ws: Workspace, gh: FakeGh):
    git(ws.main, "checkout", "-q", "-b", "feature")
    commit(ws.main, "m.txt", "m\n")
    git(ws.main, "push", "-q", "-u", "origin", "feature")

    assert big(ws).create_prs() is True
    assert gh.creates() == []

    assert big(ws).create_prs(include_main=True) is True
    assert len(gh.creates()) == 1
    assert head(ws.main)  # untouched


# ---------------------------------------------------------- edit open PRs ---


def open_pr(gh: FakeGh, body: str) -> None:
    gh.answer("open", [{"number": 5, "url": "https://x/pull/5", "baseRefName": "master",
                        "headRefOid": "abc", "body": body}])


def edits(gh: FakeGh) -> list[str]:
    log = gh.root / "calls.log"
    text = log.read_bytes().decode() if log.exists() else ""  # keep \r\n
    return [chunk.split("[--body][", 1)[1].rsplit("]", 1)[0]
            for chunk in text.split("[pr][edit][5]")[1:]]


def test_open_pr_wrong_branch_lines_are_fixed_and_free_text_kept(ws: Workspace, gh: FakeGh):
    on_feature(ws)
    write_template(ws)
    open_pr(gh, "My notes\r\n" + TEMPLATE.replace("\n", "\r\n").replace("OTHER_BRANCH=master",
                                                                       "OTHER_BRANCH=custom"))

    assert big(ws).create_prs() is True

    assert gh.creates() == []
    # SUB fixed to the submodule branch; OTHER matches no submodule, so the template's value wins
    assert edits(gh) == ["My notes\r\n" + TEMPLATE.replace("\n", "\r\n")
                         .replace("SUB_BRANCH=master", "SUB_BRANCH=feature")]


def test_open_pr_without_parameters_block_gets_it_appended(ws: Workspace, gh: FakeGh):
    on_feature(ws)
    (ws.sub / ".github").mkdir()
    (ws.sub / ".github" / "pull_request_template.md").write_text(
        "**Describe**\ntext\n\n**Parameters**\n```\nPR_START_ENV=1\nSUB_BRANCH=master\nPR_END_ENV=1\n```\n")
    open_pr(gh, "- commit one\n- commit two")

    assert big(ws).create_prs() is True

    assert edits(gh) == ["- commit one\n- commit two\n\n**Parameters**\n```\nPR_START_ENV=1\n"
                         "SUB_BRANCH=feature\nPR_END_ENV=1\n```\n"]


def test_open_pr_with_correct_body_dry_run_or_no_edit_is_not_touched(ws: Workspace, gh: FakeGh):
    on_feature(ws)
    write_template(ws)
    open_pr(gh, TEMPLATE)

    assert big(ws).create_prs(dry_run=True) is True
    assert big(ws).create_prs(edit=False) is True
    assert edits(gh) == []

    open_pr(gh, TEMPLATE.replace("SUB_BRANCH=master", "SUB_BRANCH=feature"))
    assert big(ws).create_prs() is True
    assert edits(gh) == []
