#!/bin/bash

# Set up logging
SCRIPT_NAME=$(basename "$0")
LOG_FILE="${SCRIPT_NAME%.sh}.log"
exec > >(tee -a "$LOG_FILE")
exec 2>&1

MESSAGE="$1"
curl -X POST -H 'Content-type: application/json' \
  --data "{\"text\":\"${MESSAGE}\"}" \
  "$CLAUDE_SLACK_HOOK"
