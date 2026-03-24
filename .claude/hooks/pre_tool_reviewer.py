#!/usr/bin/env python3
"""
PreToolUse hook — auto-review every tool call before execution.
Reviewer Claude approves or blocks. No human needed.
"""
import json
import subprocess
import sys

from logger import get_logger

logger = get_logger("pre_tool_reviewer")


def review(tool_name: str, tool_input: dict) -> tuple[bool, str]:
    input = json.dumps(tool_input, indent=2)
    prompt = f"""You are a strict security reviewer for an automated coding agent.
A tool is about to execute. Reply ONLY with:
- APPROVE  — if this is safe and expected for a dev/homelab workflow
- BLOCK: <reason>  — if this is destructive, irreversible, or looks wrong

Tool: {tool_name}
Input: {input}

Rules:
- APPROVE all read operations (cat, ls, grep, find, git status/diff/log)
- APPROVE file edits inside the project directory
- APPROVE docker compose up/down/logs/ps, git add/commit
- BLOCK rm -rf on anything outside /tmp or the project dir
- BLOCK git push --force, git reset --hard without explicit task context
- BLOCK writes to /etc, ~/.ssh, ~/.aws, system paths
- BLOCK any curl/wget piped to bash
"""
    result = subprocess.run(
        ["claude", "-p", prompt, "--model", "claude-haiku-4-5-20251001"],
        capture_output=True, text=True, timeout=60
    )
    logger.debug(f"Reviewer tool {tool_name}: %s", input)
    verdict = result.stdout.strip()
    logger.debug("Reviewer verdict: %s", verdict)
    approved = verdict.startswith("APPROVE")
    reason = verdict.replace("BLOCK:", "").strip() if not approved else ""
    return approved, reason


def main():
    hook_input = json.load(sys.stdin)
    tool_name = hook_input.get("tool_name", "")
    tool_input = hook_input.get("tool_input", {})

    approved, reason = review(tool_name, tool_input)

    if approved:
        logger.info("APPROVED  tool=%s", tool_name)
        sys.exit(0)
    else:
        logger.warning("BLOCKED   tool=%s reason=%s", tool_name, reason)
        print(json.dumps({"reason": reason}), file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
