# Agent + user identity: GitHub on the user's behalf

Two users ask the same `gh-agent` to open a pull request. GitHub sees each user, not
the agent: one is denied by GitHub (no write access), the other gets a PR authored in
their own name and cannot approve it. The agent holds no GitHub credential of its own.

```
Keycloak login ─▶ kagent-login ─▶ kagent ─▶ gh-agent ─▶ agentgateway ─────────────▶ github-mcp-server ─▶ GitHub
 (company login)  (forwards the   (token-    (asks for    1. verifies the user's token       (uses whatever
                   access token)  Passthrough) a GitHub    2. per-tool rules by group          token it gets)
                                              tool)      3. swaps it for the user's own
                                                            GitHub token at Keycloak
```

| Path | What it is |
|---|---|
| `keycloak/realm-lava.json` | Realm `lava`: users `shabbir-saifee-cmm` (group `sre-admin`) and `shabbir-saifee-personal` (group `sre-checkout`), client `kagent`, client `mcp-gateway`, and a GitHub identity provider (the `gh-agent` GitHub App) that stores each user's GitHub token |
| `keycloak/keycloak.yaml` | Keycloak 26 in dev mode with legacy token exchange enabled |
| `keycloak/token-exchange-permissions.sh` | Allows `mcp-gateway` to exchange a user's token for their stored GitHub token (re-run after every Keycloak restart) |
| `keycloak/kagent-login.yaml` | oauth2-proxy in front of the kagent UI, forwarding the user's **access** token (token exchange rejects ID tokens) |
| `keycloak/kagent-oidc-values.yaml` | kagent chart overlay: trusted-proxy auth, bundled oauth2-proxy off, Ingress to `kagent-login` |
| `github/agentgateway.yaml` | agentgateway: JWT check, tool rules (everything except merge, delete file, create or fork repo), token exchange |
| `github/github-mcp-server.yaml` | GitHub's MCP server in HTTP mode |
| `github/gh-agent.yaml` | The `github` RemoteMCPServer (`tokenPassthrough`) and the generic `gh-agent` |

## Setup (kind)

Secrets live in the repo's gitignored `.secrets/` folder.

1. `/etc/hosts`: `127.0.0.1 keycloak.localtest.me kagent.localtest.me` and
   `::1 keycloak.localtest.me kagent.localtest.me` (without the IPv6 line macOS waits 5s per lookup).
   In the cluster, a CoreDNS `rewrite` sends both names to the ingress controller.
2. GitHub App `gh-agent`: public, user authorization enabled, callback
   `http://keycloak.localtest.me/realms/lava/broker/github/endpoint`, Contents and Pull requests
   read/write, installed on the target repo. Client secret in `.secrets/gh-agent-client-secret.txt`.
3. Keycloak: Secret `gh-agent-oauth`, ConfigMaps `keycloak-realm` and `egress-ca-bundle` (see the
   comments in `keycloak/keycloak.yaml`), apply it, then run `keycloak/token-exchange-permissions.sh`.
4. kagent login: Secret `kagent-oidc` (`client-id`, `client-secret`, `cookie-secret`), apply
   `keycloak/kagent-login.yaml`, then
   `helm upgrade kagent oci://ghcr.io/kagent-dev/kagent/helm/kagent --version 1.0.0 -n kagent --reuse-values -f keycloak/kagent-oidc-values.yaml`.
5. Apply `github/github-mcp-server.yaml`, `github/agentgateway.yaml`, `github/gh-agent.yaml`.
6. Each user links GitHub once:
   `http://keycloak.localtest.me/realms/lava/protocol/openid-connect/auth?client_id=kagent&response_type=code&scope=openid&redirect_uri=http%3A%2F%2Fkagent.localtest.me%2Foauth2%2Fcallback&kc_action=idp_link:github`

## Run

Sign in at http://kagent.localtest.me and ask `gh-agent`, naming the repo in full:

> In <owner>/<repo>, add a line to the README saying this repo holds the agent demos, and open a PR.

Then: "Approve it." A user without write access is denied by GitHub (403); a user with access
gets a PR in their own name, and GitHub refuses the self-approval.
