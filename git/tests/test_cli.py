from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from conftest import Workspace, git, cli_env

GITTOOL = Path(__file__).resolve().parents[1] / "gittool"


def run(*args: str, cwd: Path, state: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(GITTOOL), *args],
        cwd=cwd,
        env=cli_env(XDG_STATE_HOME=str(state)),
        capture_output=True,
        text=True,
    )


def test_unknown_action_is_a_usage_error(ws: Workspace, tmp_path):
    result = run("bogus", str(ws.main), cwd=tmp_path, state=tmp_path / "state")
    assert result.returncode == 2
    assert "invalid choice" in result.stderr


def test_merge_requires_a_branch(ws: Workspace, tmp_path):
    result = run("merge", str(ws.main), cwd=tmp_path, state=tmp_path / "state")
    assert result.returncode == 2
    assert "--branch" in result.stderr


def test_path_defaults_to_cwd(ws: Workspace, tmp_path):
    result = run("verify_before_push", cwd=ws.main, state=tmp_path / "state")
    assert result.returncode == 0, result.stderr
    assert "ready to push" in result.stdout + result.stderr


def test_failed_verification_exits_nonzero_and_names_the_culprit(ws: Workspace, tmp_path):
    (ws.sub / "sub.txt").write_text("dirty\n")
    result = run("verify_before_push", str(ws.main), cwd=tmp_path, state=tmp_path / "state")
    assert result.returncode == 1
    assert "libs/sub" in result.stdout + result.stderr


def test_non_repository_path_is_a_clean_error_not_a_traceback(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    result = run("sync", str(empty), cwd=tmp_path, state=tmp_path / "state")
    assert result.returncode == 1
    assert "Traceback" not in result.stderr
    assert "not a git repository" in (result.stdout + result.stderr).lower()


def test_merge_with_conflicts_exits_nonzero(ws: Workspace, tmp_path):
    git(ws.main, "checkout", "-q", "-b", "feature")
    (ws.main / "main.txt").write_text("theirs\n")
    git(ws.main, "commit", "-q", "-am", "theirs")
    git(ws.main, "checkout", "-q", "master")
    (ws.main / "main.txt").write_text("ours\n")
    git(ws.main, "commit", "-q", "-am", "ours")

    result = run("merge", str(ws.main), "-b", "feature", cwd=tmp_path, state=tmp_path / "state")
    assert result.returncode == 1
    assert "conflict" in (result.stdout + result.stderr).lower()


def test_merge_with_ai_flag_launches_tool_and_commits(ws: Workspace, tmp_path, fake_ai):
    log = fake_ai()
    git(ws.main, "checkout", "-q", "-b", "feature")
    (ws.main / "main.txt").write_text("theirs\n")
    git(ws.main, "commit", "-q", "-am", "theirs")
    git(ws.main, "checkout", "-q", "master")
    (ws.main / "main.txt").write_text("ours\n")
    git(ws.main, "commit", "-q", "-am", "ours")

    result = run("merge", str(ws.main), "-b", "feature", "--ai", "fake-ai",
                 cwd=tmp_path, state=tmp_path / "state")

    assert result.returncode == 0, result.stderr
    assert (ws.main / "main.txt").read_text() == "resolved by ai\n"
    assert not (ws.main / ".git" / "MERGE_HEAD").exists()
    assert "main.txt" in log.read_text()


def test_no_ai_flag_is_accepted(ws: Workspace, tmp_path):
    result = run("resolve_conflicts", "--no-ai", str(ws.main), cwd=tmp_path, state=tmp_path / "state")
    assert result.returncode == 0, result.stderr


def test_remove_submodules_needs_confirmation(ws: Workspace, tmp_path):
    result = run("remove_submodules", str(ws.main), cwd=tmp_path, state=tmp_path / "state")
    assert result.returncode == 1
    assert (ws.main / "libs" / "sub" / "sub.txt").exists()

    result = run("remove_submodules", "--yes", str(ws.main), cwd=tmp_path, state=tmp_path / "state")
    assert result.returncode == 0, result.stderr
    assert not (ws.main / "libs" / "sub").exists()


def test_log_file_goes_to_state_dir_not_cwd(ws: Workspace, tmp_path):
    state = tmp_path / "state"
    run("verify_before_push", str(ws.main), cwd=tmp_path, state=state)
    assert list(tmp_path.glob("*.log")) == []
    assert list(ws.main.glob("*.log")) == []
    assert (state / "gittool" / "gittool.log").is_file()
