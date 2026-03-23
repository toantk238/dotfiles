#!/usr/bin/env python3
"""
PostToolUse hook on AskFollowupQuestion.
If it's a choice question (not a permission prompt), Reviewer Claude answers it.
Otherwise, pass through so you answer manually.
"""
import json
import re
import subprocess
import sys

from logger import get_logger

logger = get_logger("choice_reviewer")

PERMISSION_SIGNALS = [
    "do you want to proceed",
    "allow this",
    "grant permission",
    "this command requires approval",
    "yes, and don't ask again",
    "overwrite",
    "delete",
    "remove",
    "this will",
]


def looks_like_permission(question: str, options: list[str]) -> bool:
    q = question.lower()
    opts = " ".join(options).lower()
    return any(sig in q or sig in opts for sig in PERMISSION_SIGNALS)


def reviewer_pick(question: str, options: list[str], context: str) -> str:
    options_fmt = "\n".join(f"{i+1}. {o}" for i, o in enumerate(options))
    prompt = f"""You are an autonomous decision agent for a developer's coding assistant.
A question has been asked during task execution. Pick the best option and reply ONLY with the exact text of your chosen option — nothing else, no explanation.

Context of the task so far:
{context or '(no context)'}

Question:
{question}

Options:
{options_fmt}

Pick the most reasonable option for an experienced developer working on homelab/backend/Android projects.
Reply with ONLY the exact option text.
"""
    result = subprocess.run(
        ["claude", "-p", prompt, "--model", "claude-haiku-4-5"],
        capture_output=True, text=True, timeout=20
    )
    return result.stdout.strip()


def main():
    hook_input = json.load(sys.stdin)

    # Only act on AskFollowupQuestion tool
    tool_name = hook_input.get("tool_name", "")
    if tool_name != "AskFollowupQuestion":
        sys.exit(0)

    tool_input = hook_input.get("tool_input", {})
    question = tool_input.get("question", "")
    options = tool_input.get("options", [])
    context = hook_input.get("context", "")  # task history snippet

    # No options = open-ended question, let you answer
    if not options:
        logger.debug("open-ended question, skipping")
        sys.exit(0)

    # Permission-flavoured question = let you answer
    if looks_like_permission(question, options):
        logger.debug("permission question detected, skipping: %s", question[:80])
        sys.exit(0)

    # Choice question → Reviewer picks
    chosen = reviewer_pick(question, options, context)
    logger.info("AUTO-ANSWERED question=%r chosen=%r", question[:80], chosen)

    # Return the answer by writing to stdout for Claude Code to inject
    print(json.dumps({"answer": chosen, "auto_reviewed": True}))
    sys.exit(0)


if __name__ == "__main__":
    main()
