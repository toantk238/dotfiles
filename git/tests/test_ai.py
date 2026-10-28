from __future__ import annotations

import shlex
from pathlib import Path

import pytest

from helper import ai


def test_known_tools_get_their_interactive_flags():
    assert ai.tool_command("claude", "fix it") == ["claude", "fix it"]
    assert ai.tool_command("agy", "fix it") == ["agy", "-i", "fix it"]


def test_extra_tools_from_env_are_run_with_the_prompt_as_argument(monkeypatch):
    monkeypatch.setenv("GITTOOL_AI_TOOLS", "gemini, my-agent")
    assert ai.tool_command("my-agent", "fix it") == ["my-agent", "fix it"]
    assert "my-agent" in ai.known_tools() and "gemini" in ai.known_tools()


def test_unknown_tool_is_rejected():
    with pytest.raises(ValueError, match="nope"):
        ai.tool_command("nope", "fix it")


def test_tmux_launcher_waits_on_a_channel(monkeypatch):
    monkeypatch.setenv("TMUX", "/tmp/tmux-1000/default,1,0")
    monkeypatch.delenv("GITTOOL_TERMINAL", raising=False)
    cmd = ai.terminal_command(["claude", "a prompt"], Path("/work"), channel="ch1")
    assert cmd[:3] == ["tmux", "split-window", "-h"]
    script = cmd[-1]
    assert "cd /work" in script
    assert shlex.join(["claude", "a prompt"]) in script
    assert "tmux wait-for -S ch1" in script
    assert "read" in script, "the user presses Enter before the tool starts"


def test_kitty_launcher_runs_script_in_new_window(monkeypatch):
    monkeypatch.setenv("GITTOOL_TERMINAL", "kitty")
    cmd = ai.terminal_command(["agy", "-i", "p"], Path("/work"), channel="c")
    assert cmd[0] == "kitty"
    assert shlex.join(["agy", "-i", "p"]) in cmd[-1]
    assert "wait-for" not in cmd[-1]


def test_inline_launcher_runs_tool_directly(monkeypatch):
    monkeypatch.setenv("GITTOOL_TERMINAL", "inline")
    assert ai.terminal_command(["claude", "p"], Path("/work"), channel="c") == ["claude", "p"]


def test_prompt_names_files_branches_and_rules():
    prompt = ai.conflict_prompt(Path("/repo"), ours="master", theirs="feature",
                                files=["a.txt", "dir/b.py"], submodules=["libs/sub"])
    assert "/repo" in prompt
    assert "a.txt" in prompt and "dir/b.py" in prompt
    assert "'feature'" in prompt and "'master'" in prompt
    assert "libs/sub" in prompt
    assert "do not commit" in prompt.lower()
    assert "merge --abort" in prompt
