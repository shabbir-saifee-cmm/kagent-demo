#!/usr/bin/env bash
# Lets the mcp-gateway client exchange a user's kagent token for the GitHub token
# Keycloak stored when that user linked GitHub (legacy token exchange, fine-grained admin permissions v1).
# Keycloak runs in dev mode without persistence, so re-run this after every Keycloak restart.
set -euo pipefail
[ -n "${DEBUG:-}" ] && set -x
KC=${KC:-http://keycloak.localtest.me}
REALM=lava
T=$(curl -sS --fail-with-body -d client_id=admin-cli -d username=admin -d password=admin -d grant_type=password \
  "$KC/realms/master/protocol/openid-connect/token" | jq -r .access_token)
api() { curl -sS --fail-with-body -H "Authorization: Bearer $T" -H 'Content-Type: application/json' "$@"; }
A="$KC/admin/realms/$REALM"

client_id() { api "$A/clients?clientId=$1" | jq -r '.[0].id'; }
RM=$(client_id realm-management)
GW=$(client_id mcp-gateway)
KAGENT=$(client_id kagent)

enable() { api -X PUT "$1/management/permissions" -d '{"enabled":true}' | jq -r '.scopePermissions["token-exchange"]'; }
IDP_PERM=$(enable "$A/identity-provider/instances/github")
KAGENT_PERM=$(enable "$A/clients/$KAGENT")

POLICY=$(api "$A/clients/$RM/authz/resource-server/policy?name=mcp-gateway-only&exact=true" | jq -r '.[0].id // empty')
if [ -z "$POLICY" ]; then
  POLICY=$(api -X POST "$A/clients/$RM/authz/resource-server/policy/client" \
    -d "{\"name\":\"mcp-gateway-only\",\"clients\":[\"$GW\"],\"logic\":\"POSITIVE\"}" | jq -r .id)
fi

allow() {
  api "$A/clients/$RM/authz/resource-server/permission/scope/$1" \
    | jq --arg p "$POLICY" '.policies=[$p] | .decisionStrategy="UNANIMOUS"' \
    | api -X PUT "$A/clients/$RM/authz/resource-server/permission/scope/$1" -d @- -o /dev/null
  echo "token-exchange: mcp-gateway allowed on $2"
}

allow "$IDP_PERM" "identity provider github"
allow "$KAGENT_PERM" "tokens issued to kagent"
