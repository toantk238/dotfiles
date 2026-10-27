#!/usr/bin/env python3
"""
Stop hook — unified router for proceed-detection and AI-assisted question answering.
Asks Haiku first; when Haiku defers to the human, escalates once to Fable with
more of the conversation before actually handing control back.
"""
from dataclasses import dataclass, replace
import json
import os
import re
import sys
import tempfile

from common import (
    FABLE_MODEL,
    HAIKU_MODEL,
    HookInput,
    call_claude,
    get_last_assistant_message,
    get_original_user_request,
    get_recent_user_turns,
    has_incomplete_tasks,
)
from logger import get_logger, model_context

logger = get_logger("stop_router")


@dataclass(frozen=True)
class StopDecision:
    """The decision result of the stop hook."""
    action: str
    answer: str = ""
    # What Claude's last message is for: QUESTION (asks the human something),
    # REPORT (results/summary of finished work) or OTHER.
    purpose: str = "OTHER"
    # The model that made this decision ("" when no model answered).
    model: str = ""


# Each option must head its own list item ("1. Subagent-Driven", "- Native:"), as in the real
# choice prompt — not just be named in prose. "Inline Execution" was later renamed "Native".
_LIST_ITEM = r"^\s*(?:[-*\u2022]|\d+[.)]|[a-z][.)])\s*(?:\*\*)?"
_SUBAGENT = r"subagent-driven"
_NATIVE = r"(?:inline execution|native)\b"
_PLAN_SELECTION_OPTIONS = [
    re.compile(_LIST_ITEM + _SUBAGENT, re.MULTILINE),
    re.compile(_LIST_ITEM + _NATIVE, re.MULTILINE),
]
# The choice prompt must also appear as an actual question (same line, ending in "?").
# "which approach" also covers "which execution approach".
_PLAN_SELECTION_ASK = re.compile(
    r"\b(?:which (?:\w+ )?approach|which way|execution option)[^\n.]*\?")

# Claude's own recommendation, either tagged on the option ("1. Subagent-Driven (recommended)")
# or stated in prose ("I recommend subagent-driven."). Group 1 is the recommended option.
_OPTION = rf"({_SUBAGENT}|{_NATIVE})"
_RECOMMENDED_ITEM = re.compile(_LIST_ITEM + _OPTION + r"[^\n]*\(recommended\)", re.MULTILINE)
_RECOMMENDED_PROSE = re.compile(r"\brecommend(?:ed|s)?:?\s+(?:the\s+)?(?:\*\*)?" + _OPTION)


def recommended_plan_option(lowered: str) -> str | None:
    """Return the execution option Claude recommended, or None when it recommended none."""
    match = _RECOMMENDED_ITEM.search(lowered) or _RECOMMENDED_PROSE.search(lowered)
    if not match:
        return None
    option = match.group(1)
    if option.startswith("subagent"):
        return "Subagent-Driven"
    return "Native" if option == "native" else "Inline Execution"

_SPEC_WRITTEN = [
    "spec written and committed",
    "review it and let me know"
]


def check_static_rules(last_text: str) -> str | None:
    """Return an inject-context string if a known deterministic pattern matches, else None."""
    lowered = last_text.lower()
    if all(option.search(lowered) for option in _PLAN_SELECTION_OPTIONS) and \
            _PLAN_SELECTION_ASK.search(lowered):
        option = recommended_plan_option(lowered)
        if option:
            return f'{option}, as you recommended. Please continue accordingly.'
        return 'Subagent-Driven. Please continue accordingly.'
    if all(term in last_text.lower() for term in _SPEC_WRITTEN):
        return 'Specs are accepted. Please continue.'
    return None


STOP_PROMPT_TEMPLATE = """You are an autonomous decision agent for a developer's coding assistant.
Claude (the assistant) has stopped and is waiting for input.

Original user request (first message of the session):
{original_request}

Latest user message (what Claude is acting on right now):
{latest_request}

Claude's last message (may be truncated at the start):
{last_text}

Follow these steps in order to decide the best action:

STEP 0 — Is Claude finished with what the latest user message asked for?
Treat it as finished when Claude's message reports results ("Done", "Applied", "Fixed",
"Tested", "Here's why…", a summary of changes or findings) or answers a question,
EVEN IF it ends with an optional offer of further or new work, such as:
"tell me if you want it committed", "want me to also…?", "I can push/deploy/publish it",
"let me know if you'd like…", "should I commit this?".
Such offers are NOT requests for a green light — the human decides on them.
Never approve committing, pushing, deploying, publishing, deleting or other irreversible or
outward-facing actions that the user did not already ask for.
  → YES (finished, or only optional follow-ups remain): ACTION = HUMAN_NEEDED.
  → NO (Claude stopped before completing the requested task): go to STEP 1

STEP 1 — Detect options:
Does Claude's message contain a numbered or lettered list of 2 or more distinct options for the human to choose from?
  → YES: go to STEP 2
  → NO: go to STEP 3

STEP 2 — Can you pick confidently from the original request alone?
Is one option clearly the best fit given ONLY the original user request, with high confidence?
  → YES: ACTION = ANSWER. Name the specific option clearly.
  → NO or ambiguous: ACTION = HUMAN_NEEDED.

STEP 3 — Does Claude need the human's UNIQUE input that cannot be inferred?
Only flag HUMAN_NEEDED if the human must supply something Claude cannot determine:
personal preferences with no context clues, specific business/security decisions, or approval
before modifying/deleting data the human hasn't mentioned.
  → YES: ACTION = HUMAN_NEEDED.
  → NO: go to STEP 4
  Note: Rhetorical confirmations after completing work ("Does this look right?", "Any feedback?",
  "Does this look good?") are NOT genuine preference requests — treat them as green-light asks
  and go to STEP 4. Only intercept with HUMAN_NEEDED if genuinely unknowable.

STEP 4 — Is Claude asking for a green light to do work the user already requested?
Look for patterns like: "Shall I proceed?", "Ready to start?", "Want me to continue?",
"Let me know if you want me to go ahead", "I can begin implementation" — where the work
is part of the latest user request and not yet done (e.g. a plan or spec awaiting approval).
  → YES: ACTION = PROCEED.
  → NO: go to STEP 5

STEP 5 — Is this a clarifying question answerable from the original request?
Can you answer with reasonable confidence using the original request and common sense?
  → YES: ACTION = ANSWER with a concise answer.
  → NO: ACTION = HUMAN_NEEDED.

For unfinished requested work, when in doubt between PROCEED and HUMAN_NEEDED, prefer PROCEED.
For finished work (STEP 0), always choose HUMAN_NEEDED — never invent a next task.
Use ANSWER only to supply an actual answer Claude asked for, never to comment on Claude's message.

Also classify the PURPOSE of Claude's last message:
- QUESTION: it is waiting on the human to answer a question, pick an option, or approve a step.
- REPORT: it reports finished work or answers the user (optional follow-up offers included).
- OTHER: anything else.

Reply in this exact format:
ACTION: <PROCEED | ANSWER | HUMAN_NEEDED>
PURPOSE: <QUESTION | REPORT | OTHER>
ANSWER: <your concise answer if ACTION is ANSWER, reason if ACTION is HUMAN_NEEDED or PROCEED>
"""


def parse_llm_output(output: str) -> StopDecision:
    """Parse AI output for ACTION, PURPOSE and ANSWER lines. ANSWER may span multiple lines."""
    logger.debug(f"LLM raw output:\n{output}")
    action = "HUMAN_NEEDED"
    purpose = "OTHER"
    answer_lines: list[str] = []
    in_answer = False
    for line in output.splitlines():
        stripped = line.strip()
        if stripped.startswith("ACTION:"):
            action = stripped[len("ACTION:"):].strip().upper()
            in_answer = False
        elif stripped.startswith("PURPOSE:"):
            purpose = stripped[len("PURPOSE:"):].strip().upper()
            in_answer = False
        elif stripped.startswith("ANSWER:"):
            answer_lines = [stripped[len("ANSWER:"):].strip()]
            in_answer = True
        elif in_answer and stripped:
            answer_lines.append(stripped)
    answer = " ".join(part for part in answer_lines if part).strip()
    logger.debug(f"Parsed → action={action} purpose={purpose} answer={answer!r}")
    return StopDecision(action=action, answer=answer, purpose=purpose)


_STATE_FILE = os.path.join(tempfile.gettempdir(), "stop_router_last_text.json")


def _load_state() -> dict[str, str]:
    try:
        with open(_STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_state(state: dict[str, str]) -> None:
    try:
        with open(_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f)
    except Exception as e:
        logger.warning(f"Could not save state: {e}")


def check_repeated_last_text(session_id: str, last_text: str) -> bool:
    """Return True if last_text is the same as the previous one for this session."""
    if not session_id or not last_text:
        return False
    state = _load_state()
    prev = state.get(session_id)
    state[session_id] = last_text
    _save_state(state)
    if prev and prev == last_text:
        logger.info(f"Repeated last_text for session {session_id!r} — exiting to human")
        return True
    return False


ESCALATION_CONTEXT_TEMPLATE = """
A faster model already reviewed a shorter excerpt and deferred to the human, saying:
{haiku_reason}

Here is more context to decide with. Re-apply the steps above using it; only keep
HUMAN_NEEDED if the human's input is still genuinely required.

Recent user messages (oldest first):
{recent_turns}
"""


def build_prompt(last_text: str, original_request: str, latest_request: str,
                 original_limit: int = 1000, last_text_limit: int = 3000) -> str:
    # Keep the tail of the last message: the closing question/offer is what matters.
    return STOP_PROMPT_TEMPLATE.format(
        original_request=original_request[:original_limit],
        latest_request=(latest_request or original_request)[:original_limit],
        last_text=last_text[-last_text_limit:],
    )


def build_escalation_prompt(last_text: str, original_request: str, latest_request: str,
                            recent_turns: list[tuple[str, str]], haiku_reason: str) -> str:
    """The Haiku prompt with larger excerpts, recent user turns and Haiku's reason appended."""
    turns = "\n".join(f"- [{ts}] {text[:1500]}" for ts, text in recent_turns) or "(none)"
    return build_prompt(last_text, original_request, latest_request,
                        original_limit=4000, last_text_limit=12000) + \
        ESCALATION_CONTEXT_TEMPLATE.format(
            haiku_reason=haiku_reason or "(no reason given)",
            recent_turns=turns,
        )


def decide(last_text: str, original_request: str, latest_request: str = "",
           recent_turns: list[tuple[str, str]] | None = None) -> StopDecision:
    """Ask Haiku; if it defers to the human on a question, ask Fable with more context.

    Finished-work reports and other non-questions go straight to the human: Fable
    could not answer them any better, so escalating would only add latency.
    """
    with model_context(HAIKU_MODEL):
        decision = ask_model(build_prompt(last_text, original_request, latest_request),
                             HAIKU_MODEL, timeout=30)
        if decision is None:
            logger.warning("Call failed, falling back to human")
            return StopDecision(action="HUMAN_NEEDED")
        if decision.action == "PROCEED" or (decision.action == "ANSWER" and decision.answer):
            return decision
        if decision.purpose != "QUESTION":
            logger.info(f"Deferred on a non-question (purpose={decision.purpose}) — not escalating")
            return decision
        logger.info(f"Deferred on a question reason={decision.answer!r} — escalating to {FABLE_MODEL}")

    prompt = build_escalation_prompt(last_text, original_request, latest_request,
                                     recent_turns or [], decision.answer)
    with model_context(FABLE_MODEL):
        fable_decision = ask_model(prompt, FABLE_MODEL, timeout=80)
        if fable_decision is None:
            logger.warning(f"Call failed, falling back to human with {HAIKU_MODEL}'s decision")
            return decision
        return fable_decision


def ask_model(prompt: str, model: str, timeout: int) -> StopDecision | None:
    """One `model` call parsed into a decision; None when the call fails."""
    try:
        output = call_claude(prompt, model=model, timeout=timeout)
    except Exception as e:
        logger.warning(f"Call failed: {e}")
        return None
    return replace(parse_llm_output(output), model=model)


def handle_stop(last_text: str, original_request: str, latest_request: str = "",
                recent_turns: list[tuple[str, str]] | None = None) -> None:
    decision = decide(last_text, original_request, latest_request, recent_turns)

    with model_context(decision.model):
        context = ""
        if decision.action == "PROCEED":
            context = 'Your recommendation looks good. I agree. Please continue accordingly.'
        elif decision.action == "ANSWER" and decision.answer:
            context = f'{decision.answer}. Please continue accordingly.'
        else:
            logger.info(f"Passing to human (action={decision.action}) reason={decision.answer!r}")
            sys.exit(0)

        logger.info(f"Decision: action={decision.action} context={context} reason={decision.answer!r}")
    continue_with(context)


def continue_with(context: str) -> None:
    """Block the stop and hand `context` to Claude as the user's delegated reply.

    Sync Stop hook: exit 2 feeds stderr to Claude as "Stop hook feedback".
    (An asyncRewake hook would instead arrive tagged "NOT USER INPUT" and be ignored.)
    """
    print(context, file=sys.stderr)
    sys.exit(2)


def main():
    hook_input = HookInput.from_stdin()
    if not hook_input.data:
        logger.info("Early exit: empty stdin")
        sys.exit(0)

    logger.debug(f"input = {json.dumps(hook_input.data, indent=2)}")

    transcript_path = hook_input.get("transcript_path", "")
    # Check existence here (not just inside read_transcript) so we can exit early
    # with a specific "nested session" log before making two file-open attempts.
    if not transcript_path or not os.path.exists(transcript_path):
        logger.debug("Early exit: no transcript (nested session)")
        sys.exit(0)

    # background_tasks from the hook payload is the authoritative source for running
    # subagents/background work. When present as a list (even empty), trust it over the
    # transcript-based heuristic, which can generate false positives for sequential plan
    # tasks that are merely pending/in_progress as future steps.
    background_tasks = hook_input.get("background_tasks")
    if isinstance(background_tasks, list):
        # Authoritative path: payload tells us exactly what is running.
        if any(task.get("status") == "running" for task in background_tasks if isinstance(task, dict)):
            logger.info("Early exit: running background tasks/agents present in hook input")
            sys.exit(0)
    else:
        # Fallback path: background_tasks field absent (older Claude version) —
        # use transcript heuristic to detect running work.
        if has_incomplete_tasks(transcript_path):
            logger.info("Early exit: incomplete tasks present in task list (fallback heuristic)")
            sys.exit(0)

    last_text = hook_input.get("last_assistant_message", "")

    if not last_text:
        last_text = get_last_assistant_message(transcript_path)
    logger.debug(f"last_text =\n{last_text}")

    if not last_text:
        logger.info("Early exit: no last_text found")
        sys.exit(0)

    session_id = hook_input.get("session_id", "")
    # Use the payload field for repeat detection — it's always current.
    # The transcript-read last_text can be stale when the hook fires before the
    # transcript write completes, causing false repeat positives.
    # Runs before the static rules so a misfiring rule can't loop forever.
    repeat_check_text = hook_input.get("last_assistant_message", "") or last_text
    if check_repeated_last_text(session_id, repeat_check_text):
        sys.exit(0)

    static_context = check_static_rules(last_text)
    if static_context:
        logger.info(f"Static rule matched: {static_context}")
        continue_with(static_context)

    original_request = get_original_user_request(transcript_path)
    if not original_request:
        logger.info("Early exit: no original_request in transcript")
        sys.exit(0)

    recent_turns = get_recent_user_turns(transcript_path, limit=5)
    latest_request = recent_turns[-1][1] if recent_turns else ""

    handle_stop(last_text, original_request, latest_request, recent_turns)


if __name__ == "__main__":
    main()
