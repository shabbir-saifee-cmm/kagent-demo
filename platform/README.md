# Platform

What the POCs run on: a local kind cluster with kagent and Agent Substrate, plus shared
resources.

| Path | What it is |
|---|---|
| `helm/kagent-values.yaml` | kagent chart values (read-only tool RBAC plus Argo Rollouts access, tracing to Jaeger) |
| `helm/kagent-cli.yaml` | Install settings for the kagent CLI, pointing at `kagent-values.yaml` |
| `helm/substrate-atelet-kind.yaml` | Agent Substrate values for kind: atelet and the object-store plugin trust `/var/lib/ate/ca-certificates.crt` |
| `helm/prometheus-values.yaml` | Minimal Prometheus for the promotion-analysis POC |
| `shared/modelconfigs.yaml` | The `deepseek` ModelConfig (Azure AI Foundry; key from the `kagent-foundry` Secret) |
| `shared/harness.yaml` | The default `kagent` Harness |
| `observability/jaeger.yaml` | In-memory Jaeger for agent traces |

## Secrets

Everything secret lives in the repo's gitignored `.secrets/` folder and is turned into
Kubernetes Secrets by the POC scripts. Never commit it.

| File | Used for |
|---|---|
| `foundry-key` | Azure AI Foundry API key (`kagent-foundry` Secret) |
| `ca-bundle.pem` | Public roots plus the corporate TLS proxy CA, if you're behind one |
| `gh-agent-client-secret.txt` | agent-identity: the `gh-agent` GitHub App client secret |
| `github-agent-token.txt` | sandbox-agent: the agent's own GitHub token |

## Behind a TLS-inspecting proxy

Agent sandboxes reach the internet through Substrate's egress gateway, which needs to
trust the proxy's CA: run `pocs/sandbox-agent/trust-corporate-ca.sh`. Keycloak and the
GitHub MCP server read the same bundle from the `egress-ca-bundle` ConfigMap.

## Local names

The POCs use `kagent.localtest.me` and `keycloak.localtest.me`. Add both to `/etc/hosts`
for `127.0.0.1` **and** `::1` (with only IPv4, macOS waits 5 seconds per lookup), and add a
CoreDNS `rewrite` so pods resolve them to the ingress controller.
