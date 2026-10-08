#!/usr/bin/env bash
# Usage: scripts/ask-agent.sh <agent-name> "<message>"
# Requires: kubectl port-forward -n kagent svc/kagent-controller 8083:8083
set -euo pipefail

agent="$1"
message="$2"
url="${KAGENT_URL:-http://localhost:8083}/api/a2a/kagent/${agent}/"

jq -n --arg text "$message" --arg id "$(uuidgen)" '{
  jsonrpc: "2.0", id: "1", method: "message/send",
  params: {message: {role: "user", messageId: $id, parts: [{kind: "text", text: $text}]}}
}' | curl -sS -m 600 -H 'Content-Type: application/json' -d @- "$url" \
  | tee "${A2A_RAW:-/dev/null}" \
  | jq -r 'if .error then "ERROR: \(.error | tostring)"
           else ([.result.artifacts[]?.parts[]? | select(.kind == "text") | .text] | join("\n"))
                // .result.status.message.parts[0].text end'
