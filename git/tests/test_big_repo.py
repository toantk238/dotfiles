from __future__ import annotations

import pygit2
import pytest

from helper import BigRepo

from conftest import Workspace, branch_of, commit, git, head, parents_of, upstream_of


def no_prompt(prompt: str, options: list[str]) -> int | None:
    raise AssertionError(f"unexpected interactive prompt: {prompt!r} {options}")


def big(ws: Workspace, chooser=no_prompt) -> BigRepo:
    return BigRepo(ws.main, chooser=chooser)


# ---------------------------------------------------------------- sync -----


def test_sync_attaches_detached_submodule_to_branch_named_like_main(ws: Workspace):
    sha = ws.publish_sub_branch("feature", "f.txt", "f\n")
    git(ws.main, "checkout", "-q", "-b", "feature")
    ws.point_sub_at(sha)
    git(ws.main, "commit", "-q", "-m", "main: bump sub to feature")
    assert branch_of(ws.sub) == "HEAD"

    assert big(ws).sync_branch() is True

    assert branch_of(ws.sub) == "feature"
    assert head(ws.sub) == sha
    assert upstream_of(ws.sub, "feature") == "origin/feature"


def test_sync_prefers_main_branch_name_when_several_branches_point_at_commit(ws: Workspace):
    sha = ws.publish_sub_branch("feature", "f.txt", "f\n")
    ws.publish_sub_branch("other", "o.txt", "o\n", start="feature")
    # make "other" point at the same commit as "feature"
    git(ws.sub_dev, "reset", "-q", "--hard", sha)
    git(ws.sub_dev, "push", "-q", "-f", "origin", "other")
    git(ws.main, "checkout", "-q", "-b", "feature")
    ws.point_sub_at(sha)
    git(ws.main, "commit", "-q", "-m", "main: bump sub")

    assert big(ws).sync_branch() is True

    assert branch_of(ws.sub) == "feature"


def test_sync_asks_when_candidates_are_ambiguous(ws: Workspace):
    sha = ws.publish_sub_branch("a", "a.txt", "a\n")
    ws.publish_sub_branch("b", "b.txt", "b\n", start="a")
    git(ws.sub_dev, "reset", "-q", "--hard", sha)
    git(ws.sub_dev, "push", "-q", "-f", "origin", "b")
    git(ws.main, "checkout", "-q", "-b", "feature")  # main branch name matches neither a nor b
    ws.point_sub_at(sha)
    git(ws.main, "commit", "-q", "-m", "main: bump sub")

    seen: list[list[str]] = []

    def pick_b(prompt: str, options: list[str]) -> int | None:
        seen.append(options)
        return options.index("origin/b")

    assert big(ws, chooser=pick_b).sync_branch() is True

    assert seen and sorted(seen[0]) == ["origin/a", "origin/b"]
    assert branch_of(ws.sub) == "b"
    assert head(ws.sub) == sha


def test_sync_declined_prompt_leaves_submodule_detached(ws: Workspace):
    sha = ws.publish_sub_branch("a", "a.txt", "a\n")
    ws.publish_sub_branch("b", "b.txt", "b\n", start="a")
    git(ws.sub_dev, "reset", "-q", "--hard", sha)
    git(ws.sub_dev, "push", "-q", "-f", "origin", "b")
    git(ws.main, "checkout", "-q", "-b", "feature")
    ws.point_sub_at(sha)
    git(ws.main, "commit", "-q", "-m", "main: bump sub")

    assert big(ws, chooser=lambda p, o: None).sync_branch() is False

    assert branch_of(ws.sub) == "HEAD"
    assert head(ws.sub) == sha


def test_sync_never_moves_an_existing_local_branch(ws: Workspace):
    sha = ws.publish_sub_branch("feature", "f.txt", "f\n")
    git(ws.main, "checkout", "-q", "-b", "feature")
    ws.point_sub_at(sha)
    git(ws.main, "commit", "-q", "-m", "main: bump sub")
    # A local "feature" in the submodule that is ahead of origin/feature (unpushed work).
    git(ws.sub, "checkout", "-q", "-b", "feature", sha)
    ahead = commit(ws.sub, "local.txt", "wip\n")
    git(ws.sub, "checkout", "-q", "--detach", sha)

    assert big(ws).sync_branch() is False

    assert git(ws.sub, "rev-parse", "feature") == ahead
    assert branch_of(ws.sub) == "HEAD"
    assert head(ws.sub) == sha


def test_sync_fast_forwards_a_local_branch_that_is_behind_the_remote_tip(ws: Workspace):
    old = ws.publish_sub_branch("feature", "f.txt", "f\n")
    new = ws.publish_sub_branch("feature", "g.txt", "g\n", start="feature")
    git(ws.main, "checkout", "-q", "-b", "feature")
    ws.point_sub_at(new)
    git(ws.main, "commit", "-q", "-m", "main: bump sub")
    # stale local branch: an ancestor of what origin/feature (and the pointer) now is
    git(ws.sub, "branch", "feature", old)
    assert branch_of(ws.sub) == "HEAD"

    assert big(ws).sync_branch() is True

    assert branch_of(ws.sub) == "feature"
    assert head(ws.sub) == new
    assert git(ws.sub, "rev-parse", "feature") == new
    assert upstream_of(ws.sub, "feature") == "origin/feature"
    assert (ws.sub / "g.txt").exists()


def test_sync_reports_when_no_branch_points_at_submodule_commit(ws: Workspace):
    sha = ws.publish_sub_branch("feature", "f.txt", "f\n")
    git(ws.main, "checkout", "-q", "-b", "feature")
    ws.point_sub_at(sha)
    git(ws.main, "commit", "-q", "-m", "main: bump sub")
    # Remote branch moves on; the recorded commit is no longer any branch tip.
    ws.publish_sub_branch("feature", "g.txt", "g\n", start="feature")
    git(ws.sub, "fetch", "-q", "origin")

    assert big(ws).sync_branch() is False

    assert branch_of(ws.sub) == "HEAD"
    assert head(ws.sub) == sha


def test_sync_leaves_submodule_already_on_a_branch_alone(ws: Workspace):
    git(ws.sub, "checkout", "-q", "master")
    before = head(ws.sub)

    assert big(ws).sync_branch() is True

    assert branch_of(ws.sub) == "master"
    assert head(ws.sub) == before


def test_sync_initialises_missing_submodules(ws: Workspace, tmp_path):
    bare = tmp_path / "bare_clone"
    git(tmp_path, "clone", "-q", str(ws.remote_main), str(bare))
    assert not (bare / "libs" / "sub" / "sub.txt").exists()

    BigRepo(bare, chooser=no_prompt).sync_branch()

    assert (bare / "libs" / "sub" / "sub.txt").read_text() == "v1\n"
    assert branch_of(bare / "libs" / "sub") == "master"


# --------------------------------------------------- verify_before_push -----


def test_verify_before_push_passes_on_clean_pushed_tree(ws: Workspace):
    assert big(ws).verify_before_push() is True


def test_verify_before_push_fails_on_dirty_submodule(ws: Workspace):
    (ws.sub / "sub.txt").write_text("dirty\n")
    assert big(ws).verify_before_push() is False


def test_verify_before_push_fails_on_dirty_main_repo(ws: Workspace):
    (ws.main / "main.txt").write_text("dirty\n")
    assert big(ws).verify_before_push() is False


def test_verify_before_push_fails_when_submodule_commit_is_not_on_any_remote(ws: Workspace):
    git(ws.sub, "checkout", "-q", "master")
    commit(ws.sub, "local.txt", "unpushed\n")
    git(ws.main, "add", "libs/sub")
    git(ws.main, "commit", "-q", "-m", "main: bump sub to unpushed commit")

    assert big(ws).verify_before_push() is False

    git(ws.sub, "push", "-q", "origin", "master")
    assert big(ws).verify_before_push() is True


# --------------------------------------------------------------- merge -----


def test_merge_fast_forwards_when_possible(ws: Workspace):
    git(ws.main, "checkout", "-q", "-b", "feature")
    tip = commit(ws.main, "feat.txt", "x\n")
    git(ws.main, "checkout", "-q", "master")

    assert big(ws).merge("feature") is True

    assert head(ws.main) == tip
    assert branch_of(ws.main) == "master"
    assert (ws.main / "feat.txt").exists()
    assert git(ws.main, "status", "--porcelain") == ""


def test_merge_is_a_noop_when_already_up_to_date(ws: Workspace):
    git(ws.main, "branch", "old", "HEAD~1")
    before = head(ws.main)

    assert big(ws).merge("old") is True

    assert head(ws.main) == before


def test_merge_creates_merge_commit_for_diverged_branches(ws: Workspace):
    git(ws.main, "checkout", "-q", "-b", "feature")
    feature_tip = commit(ws.main, "feat.txt", "x\n")
    git(ws.main, "checkout", "-q", "master")
    master_tip = commit(ws.main, "master.txt", "y\n")

    assert big(ws).merge("feature") is True

    assert parents_of(ws.main) == [master_tip, feature_tip]
    assert git(ws.main, "log", "-1", "--format=%s") == "Merge branch 'feature' into master"
    assert (ws.main / "feat.txt").exists() and (ws.main / "master.txt").exists()
    assert git(ws.main, "status", "--porcelain") == ""
    assert not (ws.main / ".git" / "MERGE_HEAD").exists()


def test_merge_accepts_remote_tracking_branch_and_updates_submodule_checkout(ws: Workspace):
    sha = ws.publish_sub_branch("feature", "f.txt", "f\n")
    git(ws.main, "checkout", "-q", "-b", "feature")
    ws.point_sub_at(sha)
    git(ws.main, "commit", "-q", "-m", "main: bump sub")
    git(ws.main, "push", "-q", "-u", "origin", "feature")
    git(ws.main, "checkout", "-q", "master")
    git(ws.sub, "checkout", "-q", "--detach", "origin/master")
    commit(ws.main, "master.txt", "y\n")

    assert big(ws).merge("origin/feature") is True

    assert len(parents_of(ws.main)) == 2
    assert head(ws.sub) == sha, "submodule working tree must follow the merged pointer"
    assert git(ws.main, "status", "--porcelain") == ""


def test_merge_refuses_unknown_branch(ws: Workspace):
    with pytest.raises(ValueError, match="nope"):
        big(ws).merge("nope")


def test_merge_refuses_to_start_on_a_dirty_tree(ws: Workspace):
    git(ws.main, "branch", "feature")
    (ws.main / "main.txt").write_text("dirty\n")

    with pytest.raises(RuntimeError, match="uncommitted"):
        big(ws).merge("feature")


def test_merge_with_file_conflict_leaves_merge_in_progress(ws: Workspace):
    git(ws.main, "checkout", "-q", "-b", "feature")
    commit(ws.main, "main.txt", "theirs\n")
    git(ws.main, "checkout", "-q", "master")
    commit(ws.main, "main.txt", "ours\n")

    assert big(ws).merge("feature") is False

    assert (ws.main / ".git" / "MERGE_HEAD").exists()
    assert git(ws.main, "diff", "--name-only", "--diff-filter=U") == "main.txt"


# ---------------------------------------------------- resolve_conflicts -----


def _diverge_submodule(ws: Workspace, sub_branches: tuple[str, str] = ("b1", "b2"),
                       main_files: tuple[str, str] | None = None) -> tuple[str, str, str, str]:
    """main: b1 points sub at <sub_branches[0]>, b2 points sub at <sub_branches[1]>
    (non-conflicting sub changes). With main_files, each side also writes that
    content to main.txt so the main repo gets a file conflict too.
    Returns (s1, s2, b1_tip, b2_tip) and leaves main checked out on b1."""
    s1 = ws.publish_sub_branch(sub_branches[0], "one.txt", "1\n")
    s2 = ws.publish_sub_branch(sub_branches[1], "two.txt", "2\n")
    git(ws.main, "checkout", "-q", "-b", "b2")
    ws.point_sub_at(s2)
    if main_files:
        (ws.main / "main.txt").write_text(main_files[1])
        git(ws.main, "add", "main.txt")
    git(ws.main, "commit", "-q", "-m", "main: sub -> b2 side")
    b2 = head(ws.main)
    git(ws.main, "checkout", "-q", "-b", "b1", "master")
    ws.point_sub_at(s1)
    if main_files:
        (ws.main / "main.txt").write_text(main_files[0])
        git(ws.main, "add", "main.txt")
    git(ws.main, "commit", "-q", "-m", "main: sub -> b1 side")
    b1 = head(ws.main)
    return s1, s2, b1, b2


def _assert_two_step_submodule_merge(ws: Workspace, s1: str, s2_tip: str, b1: str, b2: str):
    """Quick path kept *our* pointer in the merge commit; a follow-up commit then
    records the submodule merge of their branch into ours."""
    assert parents_of(ws.main, "HEAD~1") == [b1, b2]
    assert git(ws.main, "rev-parse", "HEAD~1:libs/sub") == s1
    assert len(parents_of(ws.main)) == 1
    assert git(ws.main, "rev-parse", "HEAD:libs/sub") == head(ws.sub)
    assert sorted(parents_of(ws.sub)) == sorted([s1, s2_tip])
    assert not (ws.main / ".git" / "MERGE_HEAD").exists()
    assert not (ws.sub / ".git" / "MERGE_HEAD").exists()
    assert git(ws.main, "status", "--porcelain") == ""


def test_merge_keeps_our_submodule_then_merges_their_matching_branch(ws: Workspace):
    s1, s2, b1, b2 = _diverge_submodule(ws)

    assert big(ws).merge("b2") is True

    assert branch_of(ws.sub) == "b1"
    assert (ws.sub / "one.txt").exists() and (ws.sub / "two.txt").exists()
    _assert_two_step_submodule_merge(ws, s1, s2, b1, b2)
    assert "libs/sub" in git(ws.main, "log", "-1", "--format=%s")


def test_submodule_merge_follows_their_branch_tip_not_the_recorded_pointer(ws: Workspace):
    s1, s2_old, b1, b2 = _diverge_submodule(ws)
    # their submodule branch moved on after main recorded s2_old
    s2_new = ws.publish_sub_branch("b2", "three.txt", "3\n", start="b2")

    assert big(ws).merge("b2") is True

    _assert_two_step_submodule_merge(ws, s1, s2_new, b1, b2)
    assert (ws.sub / "three.txt").exists()


def test_submodule_merge_falls_back_to_their_commit_without_matching_branch(ws: Workspace):
    s1, s2, b1, b2 = _diverge_submodule(ws, sub_branches=("s1", "s2"))

    assert big(ws).merge("b2") is True

    assert branch_of(ws.sub) == "s1"
    _assert_two_step_submodule_merge(ws, s1, s2, b1, b2)


def test_resolve_conflicts_keeps_ours_and_leaves_file_conflicts_for_the_user(ws: Workspace):
    s1, s2, b1, b2 = _diverge_submodule(ws, main_files=("ours\n", "theirs\n"))
    repo = big(ws)

    assert repo.merge("b2") is False

    assert git(ws.main, "diff", "--name-only", "--diff-filter=U") == "main.txt"
    assert git(ws.main, "rev-parse", ":libs/sub") == s1, "our pointer is staged as the quick path"
    assert head(ws.sub) == s1, "submodule untouched until the main merge is done"
    assert (ws.main / ".git" / "MERGE_HEAD").exists()

    # the user fixes the file by hand and resumes
    (ws.main / "main.txt").write_text("both\n")
    git(ws.main, "add", "main.txt")
    assert repo.resolve_conflicts() is True

    _assert_two_step_submodule_merge(ws, s1, s2, b1, b2)
    assert (ws.main / "main.txt").read_text() == "both\n"


def test_resolve_conflicts_resumes_pending_submodule_merge_from_a_new_instance(ws: Workspace):
    s1, s2, b1, b2 = _diverge_submodule(ws, main_files=("ours\n", "theirs\n"))
    assert big(ws).merge("b2") is False
    (ws.main / "main.txt").write_text("both\n")
    git(ws.main, "add", "main.txt")

    assert big(ws).resolve_conflicts() is True  # fresh BigRepo: state must be on disk

    _assert_two_step_submodule_merge(ws, s1, s2, b1, b2)


# -------------------------------------------------------- AI resolution -----


def test_ai_tool_resolves_file_conflicts_and_merge_is_committed(ws: Workspace, fake_ai):
    log = fake_ai()
    git(ws.main, "checkout", "-q", "-b", "feature")
    commit(ws.main, "main.txt", "theirs\n")
    git(ws.main, "checkout", "-q", "master")
    commit(ws.main, "main.txt", "ours\n")

    assert BigRepo(ws.main, chooser=no_prompt, ai="fake-ai").merge("feature") is True

    assert (ws.main / "main.txt").read_text() == "resolved by ai\n"
    assert len(parents_of(ws.main)) == 2
    assert not (ws.main / ".git" / "MERGE_HEAD").exists()
    prompt = log.read_text()
    assert "main.txt" in prompt
    assert "feature" in prompt and "master" in prompt
    assert "not commit" in prompt.lower()


def test_ai_tool_is_used_for_submodule_merge_conflicts(ws: Workspace, fake_ai):
    log = fake_ai()
    s1 = ws.publish_sub_branch("b1", "shared.txt", "one\n")
    s2 = ws.publish_sub_branch("b2", "shared.txt", "two\n")
    git(ws.main, "checkout", "-q", "-b", "b2")
    ws.point_sub_at(s2)
    git(ws.main, "commit", "-q", "-m", "sub -> b2")
    b2 = head(ws.main)
    git(ws.main, "checkout", "-q", "-b", "b1", "master")
    ws.point_sub_at(s1)
    git(ws.main, "commit", "-q", "-m", "sub -> b1")
    b1 = head(ws.main)

    assert BigRepo(ws.main, chooser=no_prompt, ai="fake-ai").merge("b2") is True

    assert (ws.sub / "shared.txt").read_text() == "resolved by ai\n"
    _assert_two_step_submodule_merge(ws, s1, s2, b1, b2)
    assert "shared.txt" in log.read_text()
    assert str(ws.sub) in log.read_text()


def test_ai_tool_that_fixes_nothing_leaves_merge_in_progress(ws: Workspace, fake_ai):
    fake_ai(resolve=False)
    git(ws.main, "checkout", "-q", "-b", "feature")
    commit(ws.main, "main.txt", "theirs\n")
    git(ws.main, "checkout", "-q", "master")
    commit(ws.main, "main.txt", "ours\n")

    assert BigRepo(ws.main, chooser=no_prompt, ai="fake-ai").merge("feature") is False

    assert (ws.main / ".git" / "MERGE_HEAD").exists()
    assert git(ws.main, "diff", "--name-only", "--diff-filter=U") == "main.txt"


def test_ai_ask_mode_offers_available_tools_through_the_chooser(ws: Workspace, fake_ai):
    fake_ai()
    git(ws.main, "checkout", "-q", "-b", "feature")
    commit(ws.main, "main.txt", "theirs\n")
    git(ws.main, "checkout", "-q", "master")
    commit(ws.main, "main.txt", "ours\n")
    offered: list[list[str]] = []

    def pick_fake(prompt: str, options: list[str]) -> int | None:
        offered.append(options)
        return options.index("fake-ai")

    assert BigRepo(ws.main, chooser=pick_fake, ai="ask").merge("feature") is True

    assert offered and "fake-ai" in offered[0]
    assert (ws.main / "main.txt").read_text() == "resolved by ai\n"


def test_unknown_ai_tool_is_an_error(ws: Workspace, fake_ai):
    fake_ai()
    git(ws.main, "checkout", "-q", "-b", "feature")
    commit(ws.main, "main.txt", "theirs\n")
    git(ws.main, "checkout", "-q", "master")
    commit(ws.main, "main.txt", "ours\n")

    with pytest.raises(ValueError, match="no-such-tool"):
        BigRepo(ws.main, chooser=no_prompt, ai="no-such-tool").merge("feature")


def test_resolve_conflicts_is_a_noop_without_a_merge_in_progress(ws: Workspace):
    before = head(ws.main)
    assert big(ws).resolve_conflicts() is True
    assert head(ws.main) == before


# ---------------------------------------------------- remove_submodules -----


def test_remove_submodules_deregisters_and_deletes_them(ws: Workspace):
    big(ws).remove_submodules()

    assert not (ws.main / "libs" / "sub").exists()
    assert not (ws.main / ".git" / "modules" / "libs" / "sub").exists()
    if (ws.main / ".gitmodules").exists():
        assert "libs/sub" not in (ws.main / ".gitmodules").read_text()
    assert "libs/sub" not in git(ws.main, "ls-files")
    # the removal is staged, not committed; once committed nothing refers to it
    git(ws.main, "commit", "-q", "-m", "remove submodules")
    assert pygit2.Repository(str(ws.main)).listall_submodules() == []
    assert git(ws.main, "status", "--porcelain") == ""
