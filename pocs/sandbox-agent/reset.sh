#!/usr/bin/env bash
# Turns Demo 2 off: sandbox-agent with no network access and no GitHub token.
set -euo pipefail
CTX=${CTX:-kind-dev}
DIR=$(cd "$(dirname "$0")" && pwd)
kubectl --context "$CTX" apply -f "$DIR/sandbox-agent.yaml"
kubectl --context "$CTX" -n kagent patch agent sandbox-agent --type json -p '[{"op":"remove","path":"/spec/egressPolicyRefs"}]' 2>/dev/null || true
kubectl --context "$CTX" -n kagent delete egresspolicy github --ignore-not-found
kubectl --context "$CTX" -n kagent delete secret github-agent-token --ignore-not-found
echo "Reset: sandbox-agent has no network access. Start a new chat."
