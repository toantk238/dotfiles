#!/bin/bash

# Log one line per notification (not Slack's full JSON response)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT_NAME=$(basename "$0")
LOG_FILE="$SCRIPT_DIR/${SCRIPT_NAME%.sh}.log"
log() { echo "$(date '+%Y-%m-%d %H:%M:%S') $*" >> "$LOG_FILE"; }

read -r input
msg=$(echo "$input" | jq -r '.message')

if [ -z "$SLACK_BOT_TOKEN" ]; then
  log "skip: SLACK_BOT_TOKEN not set"
  exit 0
fi

device="${DEVICE_NAME:-$(hostname)}"
tmux_session=""
if [ -n "$TMUX" ]; then
  tmux_session=$(tmux display-message -p '#S' 2>/dev/null)
fi

prefix="[$device"
[ -n "$tmux_session" ] && prefix="$prefix | $tmux_session"
prefix="$prefix]"

full_msg="$prefix $msg"

response=$(curl -s --max-time 10 -X POST "https://slack.com/api/chat.postMessage" \
  -H "Authorization: Bearer $SLACK_BOT_TOKEN" \
  -H 'Content-type: application/json; charset=utf-8' \
  -d "$(jq -n \
    --arg channel "claude-code" \
    --arg text "$full_msg" \
    '{
      channel: $channel,
      text: $text
    }')")

if [ "$(echo "$response" | jq -r '.ok' 2>/dev/null)" = "true" ]; then
  log "sent: $full_msg"
else
  log "failed: $full_msg | $(echo "$response" | jq -rc '.error // .' 2>/dev/null || echo "$response")"
fi
exit 0
