#!/bin/bash
# ~/.claude/hooks/slack-wait-approval.sh

# Set up logging
SCRIPT_NAME=$(basename "$0")
LOG_FILE="${SCRIPT_NAME%.sh}.log"
exec > >(tee -a "$LOG_FILE")
exec 2>&1

read -r input
session_id=$(echo "$input" | jq -r '.session_id')
command=$(echo "$input" | jq -r '.tool_input.command')
value_json=$(jq -n \
  --arg session_id "$session_id" \
  --arg command "$command" \
  '{ session_id: $session_id, command: $command }' | jq -c)
curl -s -X POST "https://slack.com/api/chat.postMessage" \
  -H "Authorization: Bearer $SLACK_BOT_TOKEN" \
  -H 'Content-type: application/json' \
  -d "$(jq -n \
    --arg channel "claude-code" \
    --arg text "🚨 Command Approval Required" \
    --arg cmd "$command" \
    --arg value "$value_json" \
    '{
      channel: $channel,
      text: $text,
      blocks: [
        {
          type: "section",
          text: { type: "mrkdwn", text: "*Command:*\n```\($cmd)```" }
        },
        {
          type: "actions",
          elements: [
            {
              type: "button",
              text: { type: "plain_text", text: "✅ Approve" },
              style: "primary",
              value: $value,
              action_id: "approve_command"
            },
            {
              type: "button",
              text: { type: "plain_text", text: "❌ Deny" },
              style: "danger",
              value: $value,
              action_id: "deny_command"
            }
          ]
        }
      ]
    }')"
# Wait for file approval
approval_file="/tmp/claude-approvals/$session_id.json"
timeout=60
elapsed=0
while [ ! -f "$approval_file" ] && [ $elapsed -lt $timeout ]; do
  sleep 1
  elapsed=$((elapsed + 1))
done
if [ -f "$approval_file" ]; then
  cat "$approval_file"
  rm "$approval_file"
else
  echo '{"continue": false, "stopReason": "Slack timeout"}'
  exit 2
fi
