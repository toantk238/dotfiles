#!/bin/bash
MESSAGE="$1"
curl -X POST -H 'Content-type: application/json' \
  --data "{\"text\":\"${MESSAGE}\"}" \
  "https://hooks.slack.com/services/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"
