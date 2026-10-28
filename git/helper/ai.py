"""Hand conflicts that git cannot merge to an interactive AI coding tool.

The tool runs in its own terminal (tmux split, kitty, gnome-terminal, xterm, or
inline in the current one) with a prepared prompt. gittool blocks until that
process ends, i.e. until the user exits the tool, then re-checks the index.

Environment:
    GITTOOL_AI_TOOLS   extra tool names, comma separated; each is run as
                       ``<name> <prompt>``. Built in: claude, agy.
    GITTOOL_TERMINAL   tmux | kitty | gnome-terminal | xterm | inline.
                       Default: tmux when inside tmux, else the first installed
                       of kitty, gnome-terminal, xterm, else inline.
"""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

from .log import logger

# name -> argv builder. Interactive mode with the prompt pre-filled, so the user
# can watch the tool work.
BUILTIN_TOOLS: dict[str, Callable[[str], list[str]]] = {
    "claude": lambda prompt: ["claude", prompt],
    "agy": lambda prompt: ["agy", "-i", prompt],
}

TERMINALS = ("kitty", "gnome-terminal", "xterm")


def _extra_tools() -> list[str]:
    raw = os.environ.get("GITTOOL_AI_TOOLS", "")
    return [name.strip() for name in raw.split(",") if name.strip()]


def known_tools() -> list[str]:
    return list(BUILTIN_TOOLS) + [t for t in _extra_tools() if t not in BUILTIN_TOOLS]


def available_tools() -> list[str]:
    return [name for name in known_tools() if shutil.which(name)]


def tool_command(name: str, prompt: str) -> list[str]:
    if name in BUILTIN_TOOLS:
        return BUILTIN_TOOLS[name](prompt)
    if name in _extra_tools():
        return [name, prompt]
    raise ValueError(f"unknown AI tool '{name}'; known: {', '.join(known_tools())} "
                     f"(add more via GITTOOL_AI_TOOLS)")


def conflict_prompt(workdir: Path, ours: str, theirs: str, files: list[str],
                    submodules: list[str]) -> str:
    lines = [
        f"A git merge is in progress in {workdir}: branch '{theirs}' is being merged into '{ours}'.",
        "Resolve the conflicts in these files:",
        *[f"  - {f}" for f in files],
        "",
        "For each file, look at all three sides (`git show :1:<file>` is the common ancestor, "
        "`:2:` is ours, `:3:` is theirs) and `git log --oneline HEAD...MERGE_HEAD` for intent. "
        "Keep the intent of both sides, remove every conflict marker, and keep the project "
        "building; run the cheap relevant tests if there are any.",
        "After resolving a file, stage it with `git add <file>`.",
        "",
        "Rules:",
        "  - Do not commit, and do not run `git merge --abort` or `git reset`: gittool "
        "commits once you exit.",
        "  - Do not touch anything outside the files listed above.",
    ]
    if submodules:
        lines.append("  - Do not modify these submodule directories, they are handled separately: "
                     + ", ".join(submodules))
    lines.append("When every listed file is staged and clean, say so and exit.")
    return "\n".join(lines)


def _pick_terminal() -> str:
    chosen = os.environ.get("GITTOOL_TERMINAL")
    if chosen:
        return chosen
    if os.environ.get("TMUX") and shutil.which("tmux"):
        return "tmux"
    for name in TERMINALS:
        if shutil.which(name):
            return name
    return "inline"


def _wrapped_script(cmd: list[str], cwd: Path, epilogue: str = "") -> str:
    banner = (f"gittool: about to start {cmd[0]} in {cwd} to resolve merge conflicts. "
              "Exit the tool when you are done; gittool then commits.")
    return (f"cd {shlex.quote(str(cwd))} && printf '%s\\n' {shlex.quote(banner)} && "
            f"printf 'Press Enter to start... ' && read -r _; {shlex.join(cmd)}; {epilogue}".rstrip("; "))


def terminal_command(cmd: list[str], cwd: Path, channel: str) -> list[str]:
    """argv that opens a terminal running `cmd` in `cwd` and returns when it ends."""
    terminal = _pick_terminal()
    if terminal == "inline":
        return cmd
    if terminal == "tmux":
        script = _wrapped_script(cmd, cwd, epilogue=f"tmux wait-for -S {channel}")
        return ["tmux", "split-window", "-h", "-c", str(cwd), "sh", "-c", script]
    script = _wrapped_script(cmd, cwd)
    if terminal == "kitty":
        return ["kitty", "--directory", str(cwd), "sh", "-c", script]
    if terminal == "gnome-terminal":
        return ["gnome-terminal", "--wait", f"--working-directory={cwd}", "--", "sh", "-c", script]
    if terminal == "xterm":
        return ["xterm", "-e", "sh", "-c", script]
    raise ValueError(f"unsupported GITTOOL_TERMINAL '{terminal}'; use one of tmux, "
                     f"{', '.join(TERMINALS)}, inline")


def run_tool(name: str, prompt: str, cwd: Path) -> None:
    """Start the AI tool and block until the user exits it."""
    if not shutil.which(name):
        raise ValueError(f"AI tool '{name}' is not installed (not on PATH)")
    channel = f"gittool-{os.getpid()}"
    argv = terminal_command(tool_command(name, prompt), cwd, channel)
    logger.info("Starting %s in %s; exit it when the conflicts are resolved", name, cwd)
    logger.debug("launch: %s", argv)
    subprocess.run(argv, cwd=cwd, check=False)
    if argv[0] == "tmux":
        subprocess.run(["tmux", "wait-for", channel], check=False)
