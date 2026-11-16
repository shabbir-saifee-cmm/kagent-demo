# Promotion analysis POC

A team of kagent agents reviews every Argo Rollouts blue-green release and posts
an advisory verdict in the Argo Rollouts dashboard. It never blocks, promotes or
rolls back anything.

**What it demos:** a green deployment isn't always a good one. A release that
adds 20–40 ms to every request passes Argo's checks and a static `p95 < 100 ms`
gate, but the agents compare green against blue and flag it as AT RISK, naming
the config change that caused it.

| Path | What it is |
|---|---|
| `agents/` | `promotion-manager` and its four sub-agents (diagnostic, metrics, analysis, remediation) |
| `demo-app/` | The podinfo Rollout, its Services, the `promotion-assessment` AnalysisTemplate and a traffic generator |
| `report-service/` | Turns one agent run into the single line the dashboard shows |

Shared pieces live in `../shared/` (ModelConfig, Harness) and `../observability/` (Jaeger).
Setup, the demo script (`scripts/release.sh <version> [healthy|slow|errors]`) and known
issues are in the [root README](../../README.md).
