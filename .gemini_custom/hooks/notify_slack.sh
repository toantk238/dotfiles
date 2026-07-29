#!/bin/bash

# Set up logging
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT_NAME=$(basename "$0")
LOG_FILE="$SCRIPT_DIR/${SCRIPT_NAME%.sh}.log"
exec > >(tee -a "$LOG_FILE")
exec 2>&1

read -r input
session_id=$(echo "$input" | jq -r '.session_id')
tool_name=$(echo "$input" | jq -r '.tool_name')
msg=$(echo "$input" | jq -r '.message')

device="${DEVICE_NAME:-$(hostname)}"
tmux_session=""
if [ -n "$TMUX" ]; then
  tmux_session=$(tmux display-message -p '#S' 2>/dev/null)
fi

prefix="[$device"
[ -n "$tmux_session" ] && prefix="$prefix | $tmux_session"
prefix="$prefix]"

full_msg="$prefix $msg"

curl -s -X POST "https://slack.com/api/chat.postMessage" \
  -H "Authorization: Bearer $SLACK_BOT_TOKEN" \
  -H 'Content-type: application/json' \
  -d "$(jq -n \
    --arg channel "claude-code" \
    --arg text "$full_msg" \
    '{
      channel: $channel,
      text: $text
    }')"
