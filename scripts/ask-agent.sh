#!/usr/bin/env bash
# Usage: scripts/ask-agent.sh <agent-name> "<message>"
# Requires: kubectl port-forward -n kagent svc/kagent-controller 8083:8083
set -euo pipefail

agent="$1"
message="$2"
url="${KAGENT_URL:-http://localhost:8083}/agents/kagent/${agent}"

jq -n --arg text "$message" --arg id "$(uuidgen)" '{
  jsonrpc: "2.0", id: "1", method: "SendMessage",
  params: {message: {role: "ROLE_USER", messageId: $id, parts: [{text: $text}]}}
}' | curl -sS -m 600 -H 'Content-Type: application/json' -H 'A2A-Version: 1.0' \
      -H "X-User-Id: ${KAGENT_USER:-admin@kagent.dev}" -d @- "$url" \
  | tee "${A2A_RAW:-/dev/null}" \
  | jq -r 'if .error then "ERROR: \(.error | tostring)"
           else [.result.task.artifacts[]?.parts[]? | .text // empty] | join("") end'
