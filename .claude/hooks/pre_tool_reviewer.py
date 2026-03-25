#!/usr/bin/env python3
"""
PreToolUse hook — auto-review every tool call before execution.
Reviewer Claude approves or blocks. No human needed.
"""
import sys
import json
from dataclasses import dataclass
from common import call_claude, HookInput
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
- BLOCK rm -rf on anything outside /tmp or the project dir
- BLOCK git push --force, git reset --hard without explicit task context
- BLOCK writes to /etc, ~/.ssh, ~/.aws, system paths
- BLOCK any curl/wget piped to bash
"""

def review(tool_name: str, tool_input: dict) -> ReviewVerdict:
    formatted_input = json.dumps(tool_input, indent=2)
    prompt = REVIEW_PROMPT_TEMPLATE.format(tool_name=tool_name, tool_input=formatted_input)
    
    try:
        verdict_text = call_claude(prompt)
    except Exception as e:
        logger.error(f"Review failed due to error: {e}")
        # Default to block if review system fails? Or allow? 
        # For safety, we exit with error code 2 to block.
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
