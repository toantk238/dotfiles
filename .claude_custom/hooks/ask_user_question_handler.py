#!/usr/bin/env python3
"""
PreToolUse hook for AskUserQuestion — auto-answer using an LLM.

When Claude asks a structured question via AskUserQuestion, this hook
intercepts the call, reads the questions + options from tool_input, asks
a small LLM model to pick the best answer for each question (using the
original user request as context), and returns the answers so Claude can
continue without waiting for human input.

Exit codes:
  0  — fall through (human answers)
  0  — (with hookSpecificOutput JSON on stdout) auto-answered
"""
import json
import sys

from common import HookInput, call_claude, get_original_user_request
from logger import get_logger

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


def build_prompt(original_request: str, questions: list[dict]) -> str:
    """Format the LLM prompt."""
    questions_json = json.dumps(questions, indent=2, ensure_ascii=False)
    return ANSWER_PROMPT_TEMPLATE.format(
        original_request=original_request[:1500],
        questions_json=questions_json,
    )


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


def auto_answer(questions: list[dict], answers: dict[str, str]) -> None:
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

    prompt = build_prompt(original_request, questions)

    try:
        llm_output = call_claude(prompt, timeout=30)
    except Exception as e:
        logger.warning(f"LLM call failed, passing through to human: {e}")
        sys.exit(0)

    logger.debug(f"LLM raw output:\n{llm_output}")

    answers = parse_answers(llm_output)
    if not answers:
        logger.warning("Could not parse LLM answers, passing through to human")
        sys.exit(0)

    # Validate: ensure all questions have an answer
    missing = [q["question"] for q in questions if q.get("question") not in answers]
    if missing:
        logger.warning(f"LLM missing answers for: {missing} — passing through to human")
        sys.exit(0)

    auto_answer(questions, answers)


if __name__ == "__main__":
    main()
