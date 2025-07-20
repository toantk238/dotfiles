#!/bin/bash
# ~/.claude/hooks/slack-notify-only.sh

# Set up logging
SCRIPT_NAME=$(basename "$0")
LOG_FILE="${SCRIPT_NAME%.sh}.log"
exec > >(tee -a "$LOG_FILE")
exec 2>&1

read -r input
session_id=$(echo "$input" | jq -r '.session_id')
tool_name=$(echo "$input" | jq -r '.tool_name')
command=$(echo "$input" | jq -r '.tool_input.command')
curl -s -X POST "https://slack.com/api/chat.postMessage" \
  -H "Authorization: Bearer $SLACK_BOT_TOKEN" \
  -H 'Content-type: application/json' \
  -d "$(jq -n \
    --arg channel "claude-code" \
    --arg text "🔔 Claude ran a safe command" \
    --arg tool "$tool_name" \
    --arg cmd "$command" \
    '{
      channel: $channel,
      text: $text,
      blocks: [
        {
          type: "section",
          text: { type: "mrkdwn", text: "*Tool:* \($tool)\n*Command:*\n```\($cmd)```" }
        }
      ]
    }')" > /dev/null
echo '{"continue": true}'
