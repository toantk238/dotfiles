#!/usr/bin/env python3
"""
PreToolUse hook — auto-review every tool call before execution.
Reviewer Claude approves or blocks. No human needed.

The reviewer is deliberately biased toward the human: anything the user asked
for or approved in their own words wins over the reviewer's opinion (except a
tiny set of catastrophic commands). Approvals are remembered per session so the
same call is never blocked after having been approved once.
"""
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
import hashlib
import json
import os
import re
import sys

from common import HookInput, call_claude, get_recent_user_turns
from logger import get_logger

logger = get_logger("pre_tool_reviewer")

# How many of the user's own turns are considered "recent" for context/override.
_USER_CONTEXT_TURNS = 6
# Per-session approval state lives here; stale files are pruned after this long.
_STATE_DIR = Path(
    os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local" / "state"))
) / "claude-hooks" / "pre_tool_reviewer"
_STATE_TTL = timedelta(days=7)


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

What the user themselves said recently (oldest first):
{user_context}

Rules:
- The user is the authority. APPROVE anything they asked for, agreed to, or
  approved in the messages above — even if it looks risky out of context.
  Their explicit instruction overrides every rule below.
- APPROVE all read operations (cat, ls, grep, find, git status/diff/log)
- APPROVE file edits, remove inside the project directory, .git/sdd (related to superpower skills/agent)
- APPROVE docker compose up/down/logs/ps, git add/commit
- BLOCK rm -rf on anything outside /tmp or the project dir + associated dirs.
- BLOCK git push --force, git reset --hard without explicit task context
- BLOCK writes to /etc, ~/.ssh, ~/.aws, system paths
- When genuinely unsure, APPROVE. Blocking work the user already asked for is
  worse than letting a reversible command through.
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

# Catastrophic and unrecoverable — blocked even when the user says "go ahead".
_CRITICAL_BASH_PATTERNS = [
    (r"\brm\b\s+(-\w*r\w*f\w*|-\w*f\w*r\w*)\s+/\s*(;|&|\||$)", "rm -rf on filesystem root"),
    (r"\bmkfs(\.\w+)?\b", "filesystem format"),
    (r"\bdd\b[^\n]*\bof=/dev/(sd|nvme|hd|mmcblk)", "raw write to a block device"),
    (r":\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:", "fork bomb"),
]

# Dangerous by default, but the user can explicitly authorize them.
_BLOCK_BASH_PATTERNS = [
    (r"\brm\b\s+(-\w*r\w*f\w*|-\w*f\w*r\w*)\s+(/(?!tmp[/\s])|~/|~$|\$HOME)", "rm -rf outside safe directories"),
    (r">\s*(~/.ssh|~/.aws|/etc/)", "write to sensitive system path"),
    # (r"curl\s+\S+\s*\|\s*(bash|sh)", "remote code execution via curl-pipe"),
    # (r"wget\s+\S+\s*\|\s*(bash|sh)", "remote code execution via wget-pipe"),
]

# The user telling the agent to proceed.
_APPROVAL_PATTERNS = [
    r"\bi\s+approve\b", r"\bapproved?\b", r"\bauthoriz(e|ed)\b",
    r"\bgo\s+ahead\b", r"\bproceed\b", r"\bcarry\s+on\b",
    r"\b(do|run|execute|try)\s+(it|that|this|again)\b",
    r"\b(yes|yep|yeah|yup|ok|okay|sure|fine)\b[\s,!.]*$",
    r"\b(yes|yep|yeah|ok|okay|sure)\b[^.\n]{0,40}\b(run|do|go|proceed|continue|execute)\b",
    r"\banyway\b", r"\bunblock\b", r"\ballow\s+(it|this|that)\b",
    r"\bbypass\b", r"\bdon'?t\s+block\b", r"\bstop\s+blocking\b",
    r"\bit'?s\s+(fine|safe|ok|okay)\b",
]
_APPROVAL_RE = re.compile("|".join(_APPROVAL_PATTERNS), re.IGNORECASE)
# Negations that flip an otherwise approving-looking message.
_REFUSAL_RE = re.compile(
    r"\b(don'?t|do\s+not|never|stop|cancel|abort|revert|undo|no,)\b", re.IGNORECASE
)


# ── session state ─────────────────────────────────────────────────────────────

def _state_path(session_id: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", session_id or "default")
    return _STATE_DIR / f"{safe}.json"


def _prune_stale_state() -> None:
    cutoff = (datetime.now(timezone.utc) - _STATE_TTL).timestamp()
    try:
        for path in _STATE_DIR.glob("*.json"):
            if path.stat().st_mtime < cutoff:
                path.unlink(missing_ok=True)
    except Exception:
        pass


def _load_state(session_id: str) -> dict:
    if not session_id:
        return {}
    try:
        return json.loads(_state_path(session_id).read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_state(session_id: str, state: dict) -> None:
    if not session_id:
        # No session to key on (tests, malformed hook input) — memory only.
        return
    try:
        _STATE_DIR.mkdir(parents=True, exist_ok=True)
        _prune_stale_state()
        _state_path(session_id).write_text(json.dumps(state), encoding="utf-8")
    except Exception as e:
        logger.debug(f"Could not persist reviewer state: {e}")


def call_signature(tool_name: str, tool_input: dict) -> str:
    """Stable identity of a tool call, used as the approval-cache key."""
    try:
        payload = json.dumps(tool_input, sort_keys=True, default=str)
    except Exception:
        payload = repr(tool_input)
    return f"{tool_name}:{hashlib.sha1(payload.encode('utf-8')).hexdigest()}"


def _parse_ts(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


# ── user override ─────────────────────────────────────────────────────────────

def _command_text(tool_input: dict) -> str:
    for key in ("command", "file_path", "code", "url", "path"):
        value = tool_input.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def user_override_reason(
    tool_input: dict,
    user_turns: list[tuple[str, str]],
    last_block_at: str = "",
) -> str | None:
    """Why the human's own words authorize this call, or None.

    Two independent signals:
      * the user quoted / named the command itself → they asked for it;
      * the user said something approving *after* the last block → they are
        answering the block.
    A turn that also carries a refusal ("don't run that") never counts.
    """
    command = _normalize(_command_text(tool_input))
    block_ts = _parse_ts(last_block_at) if last_block_at else None

    for index, (timestamp, text) in enumerate(reversed(user_turns)):
        if _REFUSAL_RE.search(text):
            continue
        normalized = _normalize(text)

        if command and len(command) >= 6 and command in normalized:
            return f"user asked for this directly: {text[:160]}"

        if not _APPROVAL_RE.search(text):
            continue

        if block_ts is not None:
            turn_ts = _parse_ts(timestamp)
            # Fail open: unparseable timestamps must not silence an approval.
            if turn_ts is None or turn_ts > block_ts:
                return f"user approved after the last block: {text[:160]}"
        elif index == 0:
            # No block on record yet — only the very latest turn counts.
            return f"user approved in their latest message: {text[:160]}"

    return None


# ── review ────────────────────────────────────────────────────────────────────

@dataclass
class ReviewContext:
    """Everything the reviewer knows beyond the tool call itself."""
    session_id: str = ""
    transcript_path: str = ""
    user_turns: list[tuple[str, str]] = field(default_factory=list)
    state: dict = field(default_factory=dict)

    @classmethod
    def from_hook_input(cls, hook_input: HookInput) -> "ReviewContext":
        session_id = str(hook_input.get("session_id", "") or "")
        transcript_path = str(hook_input.get("transcript_path", "") or "")
        turns: list[tuple[str, str]] = []
        if transcript_path:
            try:
                turns = get_recent_user_turns(transcript_path, _USER_CONTEXT_TURNS)
            except Exception as e:
                logger.debug(f"Could not read user turns: {e}")
        return cls(
            session_id=session_id,
            transcript_path=transcript_path,
            user_turns=turns,
            state=_load_state(session_id),
        )

    # -- approval memory --
    def is_pre_approved(self, signature: str) -> bool:
        return signature in set(self.state.get("approved", []))

    def remember_approval(self, signature: str) -> None:
        approved = self.state.setdefault("approved", [])
        if signature not in approved:
            approved.append(signature)
            # Keep the file small; recent approvals are the ones that matter.
            self.state["approved"] = approved[-500:]
            _save_state(self.session_id, self.state)

    def record_block(self) -> None:
        self.state["last_block_at"] = datetime.now(timezone.utc).isoformat()
        _save_state(self.session_id, self.state)

    def user_context_text(self) -> str:
        if not self.user_turns:
            return "(no user messages available)"
        return "\n".join(f"- {text[:600]}" for _, text in self.user_turns)


def critical_block_reason(tool_name: str, tool_input: dict) -> str | None:
    """Unbypassable blocks — not even an explicit user approval clears these."""
    if tool_name != "Bash":
        return None
    command = tool_input.get("command", "") or ""
    for pattern, reason in _CRITICAL_BASH_PATTERNS:
        if re.search(pattern, command):
            return reason
    return None


def fast_path_decision(tool_name: str, tool_input: dict) -> str | None:
    """
    Rule-based pre-filter for obvious approve/block decisions.

    Returns:
      'APPROVE'         — deterministically safe, skip LLM
      'BLOCK: <reason>' — deterministically dangerous, skip LLM
      None              — unclear, fall through to LLM
    """
    critical = critical_block_reason(tool_name, tool_input)
    if critical:
        return f"BLOCK: {critical}"

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


def review(tool_name: str, tool_input: dict, context: ReviewContext | None = None) -> ReviewVerdict:
    context = context or ReviewContext()
    signature = call_signature(tool_name, tool_input)

    critical = critical_block_reason(tool_name, tool_input)
    if critical:
        logger.warning(f"[critical] BLOCKED  tool={tool_name} reason={critical}")
        return ReviewVerdict(approved=False, reason=critical, raw_verdict=f"BLOCK: {critical}")

    if context.is_pre_approved(signature):
        logger.info(f"[session-cache] APPROVED  tool={tool_name} (already approved this session)")
        return ReviewVerdict(approved=True, raw_verdict="APPROVE")

    override = user_override_reason(
        tool_input, context.user_turns, context.state.get("last_block_at", "")
    )
    if override:
        logger.info(f"[user-override] APPROVED  tool={tool_name} — {override}")
        context.remember_approval(signature)
        return ReviewVerdict(approved=True, reason="", raw_verdict="APPROVE")

    fast = fast_path_decision(tool_name, tool_input)
    if fast is not None:
        approved = fast == "APPROVE"
        reason = "" if approved else fast.removeprefix("BLOCK: ")
        logger.info(f"[fast-path] {'APPROVED' if approved else 'BLOCKED'}  tool={tool_name} reason={reason}")
        return ReviewVerdict(approved=approved, reason=reason, raw_verdict=fast)

    formatted_input = json.dumps(tool_input, indent=2)
    prompt = REVIEW_PROMPT_TEMPLATE.format(
        tool_name=tool_name,
        tool_input=formatted_input,
        user_context=context.user_context_text(),
    )

    try:
        verdict_text = call_claude(prompt)
    except Exception as e:
        logger.error(f"Review failed due to error, failing open (approve): {e}")
        return ReviewVerdict(approved=True, reason="", raw_verdict=f"APPROVE (reviewer error: {e})")

    logger.debug(f"Reviewer tool {tool_name}: {formatted_input}")
    logger.debug(f"Reviewer verdict: {verdict_text}")

    approved = verdict_text.startswith("APPROVE")
    reason = ""
    if not approved:
        if ":" in verdict_text:
            reason = verdict_text.split(":", 1)[1].strip()
        else:
            reason = verdict_text or "no reason provided"
    else:
        context.remember_approval(signature)

    return ReviewVerdict(approved=approved, reason=reason, raw_verdict=verdict_text)


def main():
    hook_input = HookInput.from_stdin()
    tool_name = hook_input.get("tool_name", "unknown")
    tool_input = hook_input.get("tool_input", {})

    context = ReviewContext.from_hook_input(hook_input)
    verdict = review(tool_name, tool_input, context)

    if verdict.approved:
        logger.info(f"APPROVED  tool={tool_name}")
        sys.exit(0)
    else:
        logger.warning(f"BLOCKED   tool={tool_name} reason={verdict.reason}")
        context.record_block()
        print(
            f"Tool '{tool_name}' blocked by pre_tool_reviewer.\n"
            f"Reason: {verdict.reason}\n"
            f"If this was intended, tell the user what you wanted to run — once they "
            f"approve it in their next message, the same call is allowed through.",
            file=sys.stderr,
        )
        sys.exit(2)


if __name__ == "__main__":
    main()
