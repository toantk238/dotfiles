#!/usr/bin/env python3
"""
PreToolUse hook — auto-review every tool call before execution.
Reviewer Claude approves or blocks. No human needed.
"""
from dataclasses import dataclass
import json
import re
import sys

from common import HookInput, call_claude
from logger import get_logger

logger = get_logger("pre_tool_reviewer")


@dataclass(frozen=True)
class ReviewVerdict:
    """The result of a tool review."""
    approved: bool
    reason: str = ""
    raw_verdict: str = ""


REVIEW_PROMPT_TEMPLATE = """You are a strict security reviewer for an automated coding agent.
A tool is about to execute. Reply ONLY with:
- APPROVE  — if this is safe and expected for a dev/homelab workflow
- BLOCK: <reason>  — if this is destructive, irreversible, or looks wrong

Tool: {tool_name}
Input: {tool_input}

Rules:
- APPROVE all read operations (cat, ls, grep, find, git status/diff/log)
- APPROVE file edits inside the project directory
- APPROVE docker compose up/down/logs/ps, git add/commit
- BLOCK rm -rf on anything outside /tmp or the project dir + associated dirs.
- BLOCK git push --force, git reset --hard without explicit task context
- BLOCK writes to /etc, ~/.ssh, ~/.aws, system paths
- BLOCK any curl/wget piped to bash
"""

# Tools that are always safe — never need LLM review
_ALWAYS_APPROVE_TOOLS = {
    "Read", "Glob", "Grep", "WebFetch", "WebSearch",
    "TodoRead", "TaskGet", "TaskList", "TaskOutput",
}

# Bash command prefixes that are read-only and always safe
_SAFE_BASH_PREFIXES = (
    "git status", "git log", "git diff", "git show", "git branch",
    "git remote", "ls", "cat ",  # cat reads are intentionally fast-approved (sensitive reads still go through LLM if chained)
    "find ", "which ", "echo ",
    "head ", "tail ", "wc ", "pwd", "env", "printenv",
)

# Bash patterns that are always dangerous — block without LLM
_BLOCK_BASH_PATTERNS = [
    (r"\brm\b\s+(-\w*r\w*f\w*|-\w*f\w*r\w*)\s+(/(?!tmp[/\s])|~/|~$|\$HOME)", "rm -rf outside safe directories"),
    (r">\s*(~/.ssh|~/.aws|/etc/)", "write to sensitive system path"),
    (r"curl\s+\S+\s*\|\s*(bash|sh)", "remote code execution via curl-pipe"),
    (r"wget\s+\S+\s*\|\s*(bash|sh)", "remote code execution via wget-pipe"),
]


def fast_path_decision(tool_name: str, tool_input: dict) -> str | None:
    """
    Rule-based pre-filter for obvious approve/block decisions.

    Returns:
      'APPROVE'         — deterministically safe, skip LLM
      'BLOCK: <reason>' — deterministically dangerous, skip LLM
      None              — unclear, fall through to LLM
    """
    if tool_name in _ALWAYS_APPROVE_TOOLS:
        return "APPROVE"

    if tool_name == "Bash":
        command = tool_input.get("command", "")

        for pattern, reason in _BLOCK_BASH_PATTERNS:
            if re.search(pattern, command):
                return f"BLOCK: {reason}"

        stripped = command.strip()
        if any(stripped.startswith(prefix) for prefix in _SAFE_BASH_PREFIXES):
            # Reject compound commands — shell operators could chain dangerous commands after a safe prefix
            if not re.search(r'[;&|`]|\$\(', command):
                return "APPROVE"

    return None


def review(tool_name: str, tool_input: dict) -> ReviewVerdict:
    fast = fast_path_decision(tool_name, tool_input)
    if fast is not None:
        approved = fast == "APPROVE"
        reason = "" if approved else fast.removeprefix("BLOCK: ")
        logger.info(f"[fast-path] {'APPROVED' if approved else 'BLOCKED'}  tool={tool_name} reason={reason}")
        return ReviewVerdict(approved=approved, reason=reason, raw_verdict=fast)

    formatted_input = json.dumps(tool_input, indent=2)
    prompt = REVIEW_PROMPT_TEMPLATE.format(tool_name=tool_name, tool_input=formatted_input)

    try:
        verdict_text = call_claude(prompt)
    except Exception as e:
        logger.error(f"Review failed due to error: {e}")
        sys.exit(2)

    logger.debug(f"Reviewer tool {tool_name}: {formatted_input}")
    logger.debug(f"Reviewer verdict: {verdict_text}")

    approved = verdict_text.startswith("APPROVE")
    reason = ""
    if not approved:
        if ":" in verdict_text:
            reason = verdict_text.split(":", 1)[1].strip()
        else:
            reason = verdict_text or "no reason provided"

    return ReviewVerdict(approved=approved, reason=reason, raw_verdict=verdict_text)


def main():
    hook_input = HookInput.from_stdin()
    tool_name = hook_input.get("tool_name", "unknown")
    tool_input = hook_input.get("tool_input", {})

    verdict = review(tool_name, tool_input)

    if verdict.approved:
        logger.info(f"APPROVED  tool={tool_name}")
        sys.exit(0)
    else:
        logger.warning(f"BLOCKED   tool={tool_name} reason={verdict.reason}")
        print(f"Tool '{tool_name}' blocked by pre_tool_reviewer.\nReason: {verdict.reason}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
