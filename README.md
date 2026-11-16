# kagent demos

Proofs of concept for running AI agents on our platform with
[kagent](https://kagent.dev) and [Agent Substrate](https://ate.dev): what agents can do
for platform teams, and the guardrails and identity they need to do it safely.

## POCs

| POC | What it proves |
|---|---|
| [promotion-analysis](pocs/promotion-analysis/README.md) | A team of agents reviews every blue-green release and catches regressions that pass Argo's checks |
| [sandbox-agent](pocs/sandbox-agent/README.md) | An agent in its own sandbox reaches only what we allow and uses a credential it never holds |
| [agent-identity](pocs/agent-identity/README.md) | One agent, two users: it acts with each user's own GitHub access, and PRs carry the requester's name |

## Layout

| Path | What it is |
|---|---|
| `pocs/` | One folder per POC, each with its own README (what it shows, files, setup, run) |
| `platform/` | What the POCs run on: Helm values, shared ModelConfig and Harness, Jaeger, secrets conventions |
| `deck/` | The presentations that go with the POCs |

Start with [platform](platform/README.md), then follow a POC's README. Secrets go in the
gitignored `.secrets/` folder; nothing secret is committed.
