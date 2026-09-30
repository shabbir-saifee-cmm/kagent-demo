# kagent on wild-panda

kagent, fresh, on the `wild-panda` ephemeral vcluster, with a Claude agent
authenticated via a personal Claude subscription instead of an API key.

## 1. Connect to the cluster

```bash
cd cli && go build -o lava-ephemeral . && ./lava-ephemeral connect wild-panda
```

## 2. Install kagent

Use `helm` 3.20.0 (pinned in `.tool-versions` via asdf) — newer helm builds
get their TCP connections reset on this network.

```bash
helm install kagent-crds oci://ghcr.io/kagent-dev/kagent/helm/kagent-crds --namespace kagent --create-namespace

helm install kagent oci://ghcr.io/kagent-dev/kagent/helm/kagent \
  --namespace kagent \
  --set providers.default=anthropic \
  --set k8s-agent.enabled=false \
  --set kgateway-agent.enabled=false \
  --set istio-agent.enabled=false \
  --set promql-agent.enabled=false \
  --set observability-agent.enabled=false \
  --set argo-rollouts-agent.enabled=false \
  --set helm-agent.enabled=false \
  --set cilium-policy-agent.enabled=false \
  --set cilium-manager-agent.enabled=false \
  --set cilium-debug-agent.enabled=false
```

The `*.enabled=false` flags skip every bundled demo agent — fresh cluster,
no pre-existing agents. `kubectl get agents -n kagent` should come back empty.

## 3. Deploy the Claude agent

`claude-byo-agent/` is a small custom A2A server wrapping
`@anthropic-ai/claude-agent-sdk`, deployed as a kagent **BYO Agent**
(kagent just runs the container and proxies A2A to it — model, tools, and
auth are all inside our code, not kagent config).

```bash
# 1. Get a subscription token (bills to your Claude plan, not a metered API key)
claude setup-token

# 2. Put it in a Secret (not a committed file)
kubectl create secret generic claude-byo-agent-oauth -n kagent \
  --from-literal=CLAUDE_CODE_OAUTH_TOKEN='<token from step 1>'

# 3. Build and push the image
cd claude-byo-agent
npm install && npx tsc -p tsconfig.json
docker buildx build --platform linux/amd64 -t <your-dockerhub-user>/claude-byo-agent:0.1.0 --provenance=false --push .

# 4. Deploy it
kubectl apply -f ../k8s/claude-byo-agent.yaml
```

Update the image reference in `k8s/claude-byo-agent.yaml` if you're not
pushing to `shabbirsaifee/claude-byo-agent`.

## 4. Verify

```bash
kubectl get agent claude-byo-agent -n kagent      # Ready
kubectl get pods -n kagent -l app.kubernetes.io/name=claude-byo-agent   # 1/1 Running
```

Chat with it through kagent's own UI:

```bash
kubectl port-forward -n kagent svc/kagent-ui 8080:8080
```

## Also deployed: rca-agent / remote-dev (from the other kagent-demo)

Copied over from `kagent-demo` with placeholder secrets (no real Anthropic/
GitHub creds yet — swap these for real values to actually use them):

```bash
kubectl create secret generic kagent-anthropic -n kagent \
  --from-literal=ANTHROPIC_API_KEY='<real key>'
kubectl create secret generic github-pat -n kagent \
  --from-literal=GITHUB_PERSONAL_ACCESS_TOKEN='<real token>'

kubectl apply -f k8s/modelconfig.yaml -f k8s/github-mcp.yaml \
  -f k8s/rca-agent.yaml -f k8s/remote-dev-agent.yaml
```

Deliberately **not** copied: `rbac.yaml` (targets `demo`/`argocd` namespaces
that don't exist here), `devtools-mcp.yaml` (its image only ever existed in
the local kind cluster's own registry), `devtools-rbac.yaml` (grants
cluster-admin — not applying that to a shared cluster without a separate
explicit decision), `build-infra.yaml` (same dead-end in-cluster-registry
approach already ruled out for this vcluster, see notes below).

Consequence: `remote-dev` is stuck `Accepted: False` — its tools reference
the `devtools` MCPServer, which doesn't exist here. `rca-agent` and
`github-mcp` are healthy. MCPServer/init-container pods on this cluster
also need `spec.deployment.resources` and `spec.deployment.initContainer.resources`
set explicitly (Kyverno blocks anything without them).

## Notes

- Why not kagent 1.x: its controller crash-loops on every published alpha
  ([kagent-dev/kagent#2581](https://github.com/kagent-dev/kagent/issues/2581)),
  and its native Claude runtime requires real Agent Substrate infra (gVisor
  node classes) this vcluster can't provide anyway.
- Why BYO instead of a `Declarative` agent + `ModelConfig`: kagent has no
  config path for subscription/OAuth auth, only API keys — confirmed in
  kagent's own source, on both the 0.x and 1.x lines.
- Why not the in-cluster-registry route: this vcluster's nodes can't reach
  a plain-HTTP registry (containerd requires TLS, no node-level access to
  override it) — pushed to Docker Hub instead.
