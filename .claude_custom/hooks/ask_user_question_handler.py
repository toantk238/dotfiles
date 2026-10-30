#!/usr/bin/env python3
"""
PreToolUse hook for AskUserQuestion — auto-answer using an LLM.

When Claude asks a structured question via AskUserQuestion, this hook
intercepts the call, reads the questions + options from tool_input, asks
Haiku to pick the best answer for each question (using the
original user request as context), and returns the answers so Claude can
continue without waiting for human input. If Haiku's reply is unusable
(error, unparseable, or missing answers), Opus retries once with more of the
conversation before the question falls through to the human.

Exit codes:
  0  — fall through (human answers)
  0  — (with hookSpecificOutput JSON on stdout) auto-answered
"""
import json
import sys

from common import (
    OPUS_MODEL,
    HAIKU_MODEL,
    HookInput,
    call_claude,
    get_last_assistant_message,
    get_original_user_request,
    get_recent_user_turns,
)
from logger import get_logger, model_context

logger = get_logger("ask_user_question_handler")

ANSWER_PROMPT_TEMPLATE = """\
You are an autonomous decision agent answering questions on behalf of a developer.
Claude (a coding assistant) has asked the following question(s) to the user.
Your job is to pick the best answer for each question based on the original
user request and common sense. Do NOT ask for more information — always pick one.

Original user request:
{original_request}

Questions to answer (JSON):
{questions_json}

Rules:
- For each question, you MUST pick exactly one label from the provided options list.
- For multi-select questions (multiSelect=true), you may pick multiple labels separated by commas.
- If there are no options, provide a short free-form answer.
- Reply ONLY in the following JSON format, nothing else:

{{
  "answers": {{
    "<question text>": "<chosen label or comma-separated labels>"
  }}
}}
"""


EXTRA_CONTEXT_TEMPLATE = """
More context from the conversation:

Recent user messages (oldest first):
{recent_turns}

Claude's last message before asking (may be truncated at the start):
{last_text}
"""


def build_prompt(original_request: str, questions: list[dict], original_limit: int = 1500) -> str:
    """Format the LLM prompt."""
    questions_json = json.dumps(questions, indent=2, ensure_ascii=False)
    return ANSWER_PROMPT_TEMPLATE.format(
        original_request=original_request[:original_limit],
        questions_json=questions_json,
    )


def build_extra_context(transcript_path: str) -> str:
    """Recent user turns and Claude's last message, appended to the Opus prompt."""
    if not transcript_path:
        return ""
    turns = get_recent_user_turns(transcript_path, limit=5)
    last_text = get_last_assistant_message(transcript_path) or "(none)"
    return EXTRA_CONTEXT_TEMPLATE.format(
        recent_turns="\n".join(f"- [{ts}] {text[:1500]}" for ts, text in turns) or "(none)",
        last_text=last_text[-8000:],
    )


def ask_model(prompt: str, questions: list[dict], model: str, timeout: int) -> dict[str, str] | None:
    """Ask `model` for answers; None when the call fails or any question is left unanswered.

    Every log line written while asking is tagged with `model`.
    """
    with model_context(model):
        try:
            llm_output = call_claude(prompt, model=model, timeout=timeout)
        except Exception as e:
            logger.warning(f"Call failed: {e}")
            return None

        logger.debug(f"Raw output:\n{llm_output}")

        answers = parse_answers(llm_output)
        if not answers:
            logger.warning("Could not parse answers")
            return None

        # Validate: ensure all questions have an answer
        missing = [q["question"] for q in questions if q.get("question") not in answers]
        if missing:
            logger.warning(f"Missing answers for: {missing}")
            return None
        return answers


def parse_answers(llm_output: str) -> dict[str, str] | None:
    """Extract the answers dict from LLM JSON output."""
    # Try to find a JSON block in the output
    text = llm_output.strip()
    # Strip markdown code fences if present
    if text.startswith("```"):
        lines = text.splitlines()
        # Remove first and last fence lines
        inner = [l for l in lines if not l.startswith("```")]
        text = "\n".join(inner).strip()

    try:
        parsed = json.loads(text)
        answers = parsed.get("answers")
        if isinstance(answers, dict):
            return answers
    except json.JSONDecodeError:
        logger.warning(f"Failed to parse LLM output as JSON: {text[:300]}")
    return None


def auto_answer(questions: list[dict], answers: dict[str, str], model: str) -> None:
    """Output the hookSpecificOutput JSON and exit 0 (allow + updatedInput)."""
    updated_input = {
        "questions": questions,
        "answers": answers,
    }
    output = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow",
            "updatedInput": updated_input,
        }
    }
    print(json.dumps(output))
    with model_context(model):
        logger.info(f"Auto-answered AskUserQuestion: {answers}")
    sys.exit(0)


def main() -> None:
    hook_input = HookInput.from_stdin()
    if not hook_input.data:
        logger.debug("Empty stdin, passing through")
        sys.exit(0)

    tool_name = hook_input.get("tool_name", "")
    if tool_name != "AskUserQuestion":
        # Should not happen given the matcher, but be defensive
        sys.exit(0)

    tool_input: dict = hook_input.get("tool_input", {}) or {}
    questions: list[dict] = tool_input.get("questions", [])

    if not questions:
        logger.info("No questions in tool_input, passing through")
        sys.exit(0)

    logger.debug(f"AskUserQuestion questions: {json.dumps(questions)}")

    # Try to get original request from transcript for context
    transcript_path: str = hook_input.get("transcript_path", "") or ""
    original_request = ""
    if transcript_path:
        original_request = get_original_user_request(transcript_path) or ""

    if not original_request:
        original_request = "(no additional context)"

    model = HAIKU_MODEL
    answers = ask_model(build_prompt(original_request, questions), questions, model, timeout=30)
    if answers is None:
        logger.info(f"{HAIKU_MODEL} could not answer — escalating to {OPUS_MODEL} with more context")
        model = OPUS_MODEL
        prompt = build_prompt(original_request, questions, original_limit=4000) + \
            build_extra_context(transcript_path)
        answers = ask_model(prompt, questions, model, timeout=80)
    if answers is None:
        logger.warning(f"{OPUS_MODEL} could not answer either, passing through to human")
        sys.exit(0)

    auto_answer(questions, answers, model)


if __name__ == "__main__":
    main()
