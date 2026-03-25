#!/usr/bin/env python3
import sys
import json
from logger import get_logger

logger = get_logger("debug_hook")

def main():
    try:
        input_data = sys.stdin.read()
        if not input_data:
            return

        data = json.loads(input_data)
        event = data.get("hook_event_name", "unknown_event")
        tool = data.get("tool_name", "N/A")

        logger.info(f"{event} | {json.dumps(data, indent=2)}")
    except Exception as e:
        logger.error(f"Failed to process debug hook: {e}")
    finally:
        sys.exit(0)

if __name__ == "__main__":
    main()
