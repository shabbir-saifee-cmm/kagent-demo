# kagent promotion analysis

Advisory post-promotion analysis for Argo Rollouts blue-green releases, run by
a team of native kagent agents on an ephemeral vcluster.

When a blue-green Rollout promotes, its `postPromotionAnalysis` starts a Job
that waits for the green pods to bake, then asks `promotion-manager` for a
report. The report never blocks or rolls back the release.

| Agent | Role |
|---|---|
| `promotion-manager` | Orchestrates the others and writes the final report |
| `diagnostic-agent` | Pod status, restarts, events and logs for blue vs green |
| `metrics-agent` | Prometheus golden signals (traffic, errors, latency) for blue vs green |
| `analysis-agent` | Verdict, confidence and root cause |
| `remediation-agent` | Next steps when the verdict is DEGRADED or INCONCLUSIVE |

All agents use the `deepseek` ModelConfig (Azure AI Foundry, DeepSeek-V4.1-Flash).

## Prerequisites

- A vcluster with Argo Rollouts installed (e.g. `grumpy-swan`)
- `helm` 3.20.0 (pinned in `.tool-versions`)
- A Foundry API key

## 1. Install kagent

```bash
kubectl create ns kagent
kubectl -n kagent create secret generic kagent-foundry --from-literal=FOUNDRY_API_KEY='<key>'

helm install kagent-crds oci://ghcr.io/kagent-dev/kagent/helm/kagent-crds -n kagent --version 0.10.3
helm install kagent oci://ghcr.io/kagent-dev/kagent/helm/kagent -n kagent --version 0.10.3 -f helm/kagent-values.yaml
```

The controller restarts a few times on first install until Postgres is up.

## 2. Install Prometheus

```bash
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm install prometheus prometheus-community/prometheus -n monitoring --create-namespace -f helm/prometheus-values.yaml
```

## 3. Deploy the agents

```bash
kubectl apply -f k8s/agents/
kubectl get agents -n kagent
```

If `promotion-manager` reports `remediation-agent not found`, it was created
before its sub-agents; recreate it with
`kubectl delete -f k8s/agents/promotion-manager.yaml && kubectl apply -f k8s/agents/promotion-manager.yaml`.

Smoke test:

```bash
kubectl -n kagent port-forward svc/kagent-controller 8083:8083 &
scripts/ask-agent.sh analysis-agent "Reply with just the word OK."
```

## 4. Deploy the demo app

```bash
kubectl apply -f k8s/demo/namespace.yaml
kubectl apply -f k8s/demo/
```

Release-1 is the initial deploy, so no analysis runs.

## 5. Trigger an analysis

```bash
kubectl -n demo patch rollout podinfo --type=json \
  -p='[{"op":"replace","path":"/spec/template/spec/containers/0/env/0/value","value":"release-2"}]'

kubectl -n demo get analysisrun -w
kubectl -n demo logs -l job-name --tail=-1
```

Set `PODINFO_RANDOM_ERROR=true` in a release to see a DEGRADED verdict.

## Known issues

- On host clusters whose own Argo Rollouts watches `vc-*` namespaces, the host
  controller strips `rollouts-pod-template-hash` from synced blue-green
  Services, so follow-up releases are treated as initial deploys and analysis
  never runs. Check that `podinfo-active` keeps its hash selector after release-1.
- `metrics-agent` can fail with `400 Bad Request` from the model on follow-up
  calls, leaving the report INCONCLUSIVE.
