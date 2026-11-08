"""Talk to GitHub through the `gh` CLI (it must be installed and logged in)."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from .log import logger


class GhError(RuntimeError):
    pass


def ensure_available() -> None:
    if shutil.which("gh") is None:
        raise GhError("the GitHub CLI `gh` is not installed; see https://cli.github.com")


def _gh(cwd: Path, *args: str) -> str:
    logger.debug("%s: gh %s", cwd, " ".join(args))
    result = subprocess.run(["gh", *args], cwd=cwd, capture_output=True, text=True)
    if result.returncode != 0:
        raise GhError(f"gh {args[0]} {args[1] if len(args) > 1 else ''} failed in {cwd}: "
                      f"{(result.stderr or result.stdout).strip()}")
    return result.stdout.strip()


def find_prs(cwd: Path, head: str, state: str) -> list[dict]:
    """PRs whose head branch is `head` in `state` (open, merged, closed, all)."""
    out = _gh(cwd, "pr", "list", "--head", head, "--state", state,
              "--json", "number,url,baseRefName,headRefOid,body")
    return json.loads(out) if out else []


# Where GitHub looks for a single PR template (file name is case-insensitive).
TEMPLATE_DIRS = (".github", ".", "docs")
TEMPLATE_NAME = "pull_request_template.md"


def find_template(workdir: Path) -> Path | None:
    """The repo's PR template: <dir>/pull_request_template.md in .github, root or
    docs, else the first file in <dir>/PULL_REQUEST_TEMPLATE/. None if there is none."""
    for folder in TEMPLATE_DIRS:
        base = workdir / folder
        if not base.is_dir():
            continue
        for entry in sorted(base.iterdir()):
            if entry.is_file() and entry.name.lower() == TEMPLATE_NAME:
                return entry
        for entry in sorted(base.iterdir()):
            if entry.is_dir() and entry.name.lower() == "pull_request_template":
                files = sorted(f for f in entry.iterdir() if f.is_file() and f.suffix.lower() == ".md")
                if files:
                    return files[0]
    return None


def create_pr(cwd: Path, head: str, base: str, title: str, body: str, draft: bool) -> str:
    """Open a PR from `head` into `base`. Returns the PR URL."""
    args = ["pr", "create", "--head", head, "--base", base, "--title", title, "--body", body]
    if draft:
        args.append("--draft")
    out = _gh(cwd, *args)
    return out.splitlines()[-1] if out else ""


def edit_pr_body(cwd: Path, number: int, body: str) -> None:
    _gh(cwd, "pr", "edit", str(number), "--body", body)
