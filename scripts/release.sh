#!/usr/bin/env bash
# Usage: scripts/release.sh <version> [healthy|slow|errors]
#   healthy  normal release (default)
#   slow     adds 20-40ms latency per request: Argo passes, the agents flag it AT RISK
#   errors   returns random 5xx: the agents flag it DEGRADED
set -euo pipefail

version="$1"
mode="${2:-healthy}"
ns=demo
rollout=demo-app

case "$mode" in
  healthy) delay=false errors=false ;;
  slow)    delay=true  errors=false ;;
  errors)  delay=false errors=true ;;
  *) echo "unknown mode: $mode (healthy|slow|errors)" >&2; exit 1 ;;
esac

patch=$(kubectl -n "$ns" get rollout "$rollout" -o json | jq -c \
  --arg version "$version" --arg delay "$delay" --arg errors "$errors" '
  .spec.template.spec.containers[0].env
  | to_entries
  | map(
      if .value.name == "PODINFO_UI_MESSAGE" then {op: "replace", path: "/spec/template/spec/containers/0/env/\(.key)/value", value: $version}
      elif .value.name == "PODINFO_RANDOM_DELAY" then {op: "replace", path: "/spec/template/spec/containers/0/env/\(.key)/value", value: $delay}
      elif .value.name == "PODINFO_RANDOM_ERROR" then {op: "replace", path: "/spec/template/spec/containers/0/env/\(.key)/value", value: $errors}
      else empty end)')

kubectl -n "$ns" patch rollout "$rollout" --type=json -p "$patch"
echo "Released $version ($mode). Watch: kubectl argo rollouts get rollout $rollout -n $ns --watch"
