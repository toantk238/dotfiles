#!/usr/bin/env python3
import json
import sys

from common import HookInput
from logger import get_logger

logger = get_logger("debug_hook")


def main():
    hook_input = HookInput.from_stdin()
    if not hook_input.data:
        return

    event = hook_input.get("hook_event_name", "unknown_event")
    tool = hook_input.get("tool_name", "N/A")

    try:
        logger.info(f"{event} | tool={tool} | {json.dumps(hook_input.data, indent=2)}")
    except Exception as e:
        logger.error(f"Failed to log debug info: {e}")
    finally:
        sys.exit(0)


if __name__ == "__main__":
    main()
