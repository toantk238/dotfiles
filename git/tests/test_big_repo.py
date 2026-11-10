from __future__ import annotations

import subprocess

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
    git(ws.sub, "checkout", "-q", "master")
    commit(ws.main, "master.txt", "y\n")

    assert big(ws).merge("origin/feature") is True

    assert len(parents_of(ws.main)) == 2
    assert head(ws.sub) == sha, "submodule checkout must follow the merged pointer"
    assert branch_of(ws.sub) == "feature", "their submodule branch is checked out"
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


# ---------------------------------------------------- submodule merges -----


def _diverge_submodule(ws: Workspace, sub_branches: tuple[str, str] = ("b1", "b2"),
                       main_files: tuple[str, str] | None = None,
                       sub_file: str | None = None) -> tuple[str, str, str, str]:
    """main: b1 points sub at <sub_branches[0]>, b2 points sub at <sub_branches[1]>
    (non-conflicting sub changes, or both editing `sub_file` when given). With
    main_files, each side also writes that content to main.txt so the main repo
    gets a file conflict too. Returns (s1, s2, b1_tip, b2_tip) and leaves main on
    b1 with the submodule on branch <sub_branches[0]>."""
    s1 = ws.publish_sub_branch(sub_branches[0], sub_file or "one.txt", "1\n")
    s2 = ws.publish_sub_branch(sub_branches[1], sub_file or "two.txt", "2\n")
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
    git(ws.sub, "checkout", "-q", sub_branches[0])
    return s1, s2, b1, b2


def _assert_merged_with_submodule(ws: Workspace, s1: str, s2: str, b1: str, b2: str):
    """One main merge commit that records the submodule's own merge of s1 + s2."""
    assert parents_of(ws.main) == [b1, b2]
    assert git(ws.main, "rev-parse", "HEAD:libs/sub") == head(ws.sub)
    assert parents_of(ws.sub) == [s1, s2]
    assert not (ws.main / ".git" / "MERGE_HEAD").exists()
    assert not (ws.main / ".git" / "modules" / "libs" / "sub" / "MERGE_HEAD").exists()
    assert git(ws.main, "status", "--porcelain") == ""


def _assert_nothing_changed(ws: Workspace, b1: str, s1: str, sub_branch: str = "b1"):
    assert head(ws.main) == b1
    assert head(ws.sub) == s1
    assert branch_of(ws.sub) == sub_branch
    assert not (ws.main / ".git" / "MERGE_HEAD").exists()
    assert git(ws.main, "status", "--porcelain") == ""


def test_merge_merges_submodule_first_then_records_it_in_the_main_merge(ws: Workspace):
    s1, s2, b1, b2 = _diverge_submodule(ws)

    assert big(ws).merge("b2") is True

    assert branch_of(ws.sub) == "b1", "the submodule stays on its branch"
    assert (ws.sub / "one.txt").exists() and (ws.sub / "two.txt").exists()
    _assert_merged_with_submodule(ws, s1, s2, b1, b2)


def test_merge_takes_the_recorded_submodule_commit_not_the_branch_tip(ws: Workspace):
    s1, s2, b1, b2 = _diverge_submodule(ws)
    # their submodule branch moved on after main recorded s2
    ws.publish_sub_branch("b2", "three.txt", "3\n", start="b2")

    assert big(ws).merge("b2") is True

    _assert_merged_with_submodule(ws, s1, s2, b1, b2)
    assert not (ws.sub / "three.txt").exists()


def test_merge_does_not_need_a_submodule_branch_named_like_the_main_one(ws: Workspace):
    s1, s2, b1, b2 = _diverge_submodule(ws, sub_branches=("s1", "s2"))

    assert big(ws).merge("b2") is True

    assert branch_of(ws.sub) == "s1"
    _assert_merged_with_submodule(ws, s1, s2, b1, b2)


def test_merge_refuses_when_a_changed_submodule_is_not_on_a_branch(ws: Workspace):
    s1, s2, b1, b2 = _diverge_submodule(ws)
    git(ws.sub, "checkout", "-q", "--detach")

    assert big(ws).merge("b2") is False

    _assert_nothing_changed(ws, b1, s1, sub_branch="HEAD")


def test_merge_refuses_when_the_submodule_merge_would_conflict(ws: Workspace):
    s1, s2, b1, b2 = _diverge_submodule(ws, sub_file="shared.txt")

    assert big(ws).merge("b2") is False

    _assert_nothing_changed(ws, b1, s1)
    assert git(ws.sub, "status", "--porcelain") == ""


def test_merge_refuses_on_a_dirty_submodule(ws: Workspace):
    s1, s2, b1, b2 = _diverge_submodule(ws)
    (ws.sub / "one.txt").write_text("dirty\n")

    with pytest.raises(RuntimeError, match="uncommitted"):  # main sees the submodule as modified
        big(ws).merge("b2")

    assert head(ws.main) == b1 and head(ws.sub) == s1


def _sub_ahead_on_b2(ws: Workspace, sub_branch: str = "b2") -> tuple[str, str, str]:
    """main b2 points sub at s2, one commit ahead of the sub's master (s1), published
    on sub branch <sub_branch>. Leaves main on master. Returns (s1, s2, b2_tip)."""
    s1 = head(ws.sub)
    s2 = ws.publish_sub_branch(sub_branch, "two.txt", "2\n")
    git(ws.main, "checkout", "-q", "-b", "b2")
    ws.point_sub_at(s2)
    git(ws.main, "commit", "-q", "-m", "main: sub -> b2")
    b2 = head(ws.main)
    git(ws.main, "checkout", "-q", "master")
    return s1, s2, b2


def test_merge_checks_out_the_submodule_branch_at_their_commit_when_it_contains_ours(ws: Workspace):
    s1, s2, b2 = _sub_ahead_on_b2(ws)
    git(ws.sub, "checkout", "-q", "master")

    assert big(ws).merge("b2") is True

    assert head(ws.main) == b2, "main fast-forwards too"
    assert head(ws.sub) == s2 and branch_of(ws.sub) == "b2"
    assert upstream_of(ws.sub, "b2") == "origin/b2"
    assert git(ws.sub, "rev-parse", "master") == s1, "our submodule branch is not moved"
    assert git(ws.main, "status", "--porcelain") == ""


def test_merge_checks_out_their_branch_even_from_a_detached_submodule(ws: Workspace):
    s1, s2, b2 = _sub_ahead_on_b2(ws)
    git(ws.sub, "checkout", "-q", "--detach", s1)
    assert git(ws.main, "status", "--porcelain") == ""

    assert big(ws).merge("b2") is True

    assert head(ws.sub) == s2 and branch_of(ws.sub) == "b2"
    assert git(ws.main, "status", "--porcelain") == ""


def test_merge_prefers_the_submodule_branch_named_like_the_merged_one(ws: Workspace):
    s1, s2, b2 = _sub_ahead_on_b2(ws)
    git(ws.sub_dev, "push", "-q", "origin", "b2:other")
    git(ws.sub, "checkout", "-q", "master")

    assert big(ws).merge("b2") is True  # no_prompt: two candidates must not ask

    assert branch_of(ws.sub) == "b2"


def test_merge_fast_forwards_the_current_submodule_branch_when_no_branch_is_at_their_commit(
        ws: Workspace):
    s1, s2, b2 = _sub_ahead_on_b2(ws)
    ws.publish_sub_branch("b2", "three.txt", "3\n", start="b2")  # b2 moved past s2
    git(ws.sub, "fetch", "-q", "origin")
    git(ws.sub, "checkout", "-q", "master")

    assert big(ws).merge("b2") is True

    assert head(ws.sub) == s2 and branch_of(ws.sub) == "master"
    assert git(ws.main, "status", "--porcelain") == ""


def test_merge_ignores_detached_submodules_the_merge_does_not_touch(ws: Workspace):
    git(ws.main, "checkout", "-q", "-b", "feature")
    tip = commit(ws.main, "feat.txt", "x\n")
    git(ws.main, "checkout", "-q", "master")
    assert branch_of(ws.sub) == "HEAD"

    assert big(ws).merge("feature") is True

    assert head(ws.main) == tip


def test_resolve_conflicts_finishes_after_file_conflicts_with_submodule_already_merged(ws: Workspace):
    s1, s2, b1, b2 = _diverge_submodule(ws, main_files=("ours\n", "theirs\n"))
    repo = big(ws)

    assert repo.merge("b2") is False

    assert git(ws.main, "diff", "--name-only", "--diff-filter=U") == "main.txt"
    assert parents_of(ws.sub) == [s1, s2], "submodule was merged before the main repo"
    assert git(ws.main, "rev-parse", ":libs/sub") == head(ws.sub), "its merge is staged"
    assert (ws.main / ".git" / "MERGE_HEAD").exists()

    (ws.main / "main.txt").write_text("both\n")
    git(ws.main, "add", "main.txt")
    assert big(ws).resolve_conflicts() is True  # fresh BigRepo: state must be on disk

    _assert_merged_with_submodule(ws, s1, s2, b1, b2)
    assert (ws.main / "main.txt").read_text() == "both\n"


def test_resolve_conflicts_records_a_submodule_merged_by_hand_after_plain_git_merge(ws: Workspace):
    s1, s2, b1, b2 = _diverge_submodule(ws)
    git(ws.sub, "merge", "-q", "--no-edit", s2)
    with pytest.raises(subprocess.CalledProcessError):
        git(ws.main, "merge", "b2")  # stops on the libs/sub pointer conflict

    assert big(ws).resolve_conflicts() is True

    _assert_merged_with_submodule(ws, s1, s2, b1, b2)


def test_resolve_conflicts_keeps_a_submodule_conflict_whose_checkout_lacks_a_side(ws: Workspace):
    _diverge_submodule(ws)
    with pytest.raises(subprocess.CalledProcessError):
        git(ws.main, "merge", "b2")

    assert big(ws).resolve_conflicts() is False

    assert git(ws.main, "diff", "--name-only", "--diff-filter=U") == "libs/sub"


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


def test_ai_tool_is_not_used_for_submodule_conflicts(ws: Workspace, fake_ai):
    log = fake_ai()
    s1, s2, b1, b2 = _diverge_submodule(ws, sub_file="shared.txt")

    assert BigRepo(ws.main, chooser=no_prompt, ai="fake-ai").merge("b2") is False

    _assert_nothing_changed(ws, b1, s1)
    assert not log.exists()


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
