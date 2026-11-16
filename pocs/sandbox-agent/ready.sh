#!/usr/bin/env bash
# Demo 2 ready state: sandbox-agent can reach only the GitHub API, using its own
# token (from .secrets/github-agent-token.txt) added by Substrate's egress gateway.
set -euo pipefail
CTX=${CTX:-kind-dev}
DIR=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$DIR/../.." && pwd)
kubectl --context "$CTX" -n kagent create secret generic github-agent-token \
  --from-file=token=<(tr -d '\n\r ' < "$ROOT/.secrets/github-agent-token.txt") \
  --dry-run=client -o yaml | kubectl --context "$CTX" apply -f - >/dev/null
kubectl --context "$CTX" apply -f "$DIR/egresspolicy-github.yaml" -f "$DIR/sandbox-agent.yaml"
echo "Ready: sandbox-agent reaches only api.github.com, as its own GitHub identity."
