# kagent promotion analysis

Advisory post-promotion analysis for Argo Rollouts blue-green releases, run by
a team of native kagent agents on an ephemeral vcluster.

When the `demo-app` Rollout promotes, its `postPromotionAnalysis` waits for the
green pods to bake, then asks the agents to compare the new (green) version with
the old (blue) one. The verdict shows up in the Argo Rollouts dashboard as one
`promotion-assessment` line:

| Verdict | Dashboard | Meaning |
|---|---|---|
| HEALTHY | green | No difference that matters |
| AT RISK | yellow | Nothing is broken, but green is clearly worse than blue (e.g. 10x slower) |
| INCONCLUSIVE | yellow | Not enough traffic or data, or the agents timed out |
| DEGRADED | red | Errors, crashes or a large latency regression; includes the rollback command |

The analysis is `dryRun`: it never blocks, promotes or rolls back the release.

| Agent | Role |
|---|---|
| `promotion-manager` | Orchestrates the others over A2A and returns the final report as JSON |
| `diagnostic-agent` | Pods, restarts, events and logs for blue vs green, plus a diff of the two pod templates |
| `metrics-agent` | Prometheus golden signals (traffic, errors, latency) for blue vs green |
| `analysis-agent` | Verdict, confidence and root cause |
| `remediation-agent` | The next step when the verdict is AT RISK or DEGRADED |

All agents use the `deepseek` ModelConfig (Azure AI Foundry, DeepSeek-V4.1-Flash).

## How it works

```
Rollout promotes ─▶ AnalysisRun (web metric, after a 90s bake)
                      │
                      ▼
                 report-service ──A2A──▶ promotion-manager ─▶ diagnostic / metrics / analysis / remediation agents
                      │                                        (Kubernetes + Prometheus via kagent's MCP tool server)
                      ▼
       "AT RISK · 88% confidence: ..."  ─▶  Argo Rollouts dashboard
```

`report-service` (Python stdlib, code mounted from a ConfigMap) turns one agent
run into the single line the dashboard shows. It shares one run across
concurrent requests, gives each attempt 120s, retries once, and returns
INCONCLUSIVE rather than hanging if the model stalls. It also prints the full
agent trace to its logs. Every agent sends OpenTelemetry traces to Jaeger.

## Prerequisites

- A vcluster with Argo Rollouts v1.7+ installed (the dashboard's analysis view needs 1.7)
- `kubectl`, the `kubectl argo rollouts` plugin, `jq`
- `helm` 3.20.0 (pinned in `.tool-versions`)
- A Foundry API key

## 1. Store the Foundry key

```bash
printf '%s' '<key>' > .foundry-key     # gitignored
```

## 2. Install Jaeger

Install it before kagent: kagent is configured to send traces to it.

```bash
kubectl apply -f k8s/observability/jaeger.yaml
kubectl -n observability rollout status deploy/jaeger
```

## 3. Install kagent

```bash
kubectl create ns kagent
kubectl -n kagent create secret generic kagent-foundry --from-file=FOUNDRY_API_KEY=.foundry-key

helm install kagent-crds oci://ghcr.io/kagent-dev/kagent/helm/kagent-crds -n kagent --version 0.10.3
helm install kagent oci://ghcr.io/kagent-dev/kagent/helm/kagent -n kagent --version 0.10.3 -f helm/kagent-values.yaml
kubectl -n kagent rollout status deploy/kagent-controller
```

The controller restarts a few times on first install until Postgres is up.

## 4. Install Prometheus

```bash
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm install prometheus prometheus-community/prometheus -n monitoring --create-namespace -f helm/prometheus-values.yaml
```

## 5. Deploy the agents and report-service

Create the sub-agents before `promotion-manager`, which references them:

```bash
cd k8s/agents
kubectl apply -f modelconfigs.yaml -f rbac.yaml \
  -f diagnostic-agent.yaml -f metrics-agent.yaml -f analysis-agent.yaml -f remediation-agent.yaml
kubectl apply -f promotion-manager.yaml
cd ../..
kubectl get agents -n kagent            # all five should be READY=True

kubectl apply -k report-service
kubectl -n kagent rollout status deploy/report-service
```

If `promotion-manager` still reports `remediation-agent not found`, recreate it:
`kubectl delete -f k8s/agents/promotion-manager.yaml && kubectl apply -f k8s/agents/promotion-manager.yaml`.

Optional smoke test:

```bash
kubectl -n kagent port-forward svc/kagent-controller 8083:8083 &
scripts/ask-agent.sh analysis-agent "Reply with just the word OK."
```

## 6. Deploy the demo app

```bash
kubectl apply -f k8s/demo/namespace.yaml
kubectl apply -f k8s/demo/
```

`demo-app` (a podinfo container) starts as `release-1`, the initial deploy, so
no analysis runs. A traffic generator keeps requests flowing.

## 7. Release and watch

Open the dashboards, each in its own terminal:

```bash
kubectl argo rollouts dashboard -n demo                      # http://localhost:3100/rollouts → demo-app
kubectl -n observability port-forward svc/jaeger 16686:16686   # http://localhost:16686
```

Release a new version:

```bash
scripts/release.sh <version> [healthy|slow|errors]
```

| Mode | What changes | Expected verdict |
|---|---|---|
| `healthy` (default) | Only the version label | HEALTHY |
| `slow` | Adds 20–40 ms to every request; Argo still reports Healthy | AT RISK |
| `errors` | Returns random 5xx | DEGRADED |

Each version name must differ from the current one, or nothing is released
(for example `release-2`, `release-3 slow`, `release-4`). After a `slow` or
`errors` release, run a `healthy` one before the next scenario, because the
agents compare against the previous version.

A run takes about 90s of bake plus 40–55s of agent work. To see the result:

- **Argo Rollouts dashboard:** demo-app → the latest analysis → `promotion-assessment`.
- **Jaeger:** service `promotion_manager` → Find Traces. One trace covers the whole
  chain: each agent, every tool call (Prometheus queries, pod logs, YAML reads)
  and every model call.
- **Logs:** `kubectl -n kagent logs deploy/report-service` prints each agent's
  request, tool calls and reply, then the final report.

## Slides

`deck/index.html` is the presentation that goes with the demo. Open it in a
browser; use the arrow keys to navigate and `F` for fullscreen. `#4` opens the
slide that follows the live demo.

## Known issues

- On host clusters whose own Argo Rollouts watches `vc-*` namespaces, the host
  controller strips `rollouts-pod-template-hash` from synced blue-green
  Services, so follow-up releases are treated as initial deploys and analysis
  never runs. Check that `demo-app-active` keeps its hash selector after release-1.
- Foundry calls occasionally stall for minutes. report-service retries once;
  if both attempts stall the verdict is INCONCLUSIVE ("The agents did not finish").
  Re-release to try again.
- Jaeger stores traces in memory; they are lost if its pod restarts.
