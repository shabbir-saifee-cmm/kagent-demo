#!/usr/bin/env bash
# Local workaround for a corporate TLS-inspecting proxy: Substrate's egress gateway
# verifies upstream servers against /etc/ssl/certs/ca-certificates.crt, which lacks the
# corporate CA, so calls fail with "invalid peer certificate: UnknownIssuer".
# The Substrate chart has no setting for extra CAs, so this patches the Helm-managed
# Deployment; re-run after any Substrate upgrade.
# Usage: trust-corporate-ca.sh [ca-bundle.pem]   (default: .secrets/ca-bundle.pem)
set -euo pipefail
BUNDLE=${1:-$(cd "$(dirname "$0")/../.." && pwd)/.secrets/ca-bundle.pem}
CTX=${CTX:-kind-dev}
kubectl --context "$CTX" -n ate-system create configmap egress-ca-bundle \
  --from-file=ca-certificates.crt="$BUNDLE" --dry-run=client -o yaml | kubectl --context "$CTX" apply --server-side --force-conflicts -f -
kubectl --context "$CTX" -n ate-system patch deployment atenet-egress --type strategic -p '{
  "spec": {"template": {"spec": {
    "volumes": [{"name": "corporate-ca", "configMap": {"name": "egress-ca-bundle"}}],
    "containers": [{"name": "agentgateway", "volumeMounts": [
      {"name": "corporate-ca", "mountPath": "/etc/ssl/certs/ca-certificates.crt", "subPath": "ca-certificates.crt", "readOnly": true}
    ]}]
  }}}}'
kubectl --context "$CTX" -n ate-system rollout status deployment/atenet-egress --timeout=180s
