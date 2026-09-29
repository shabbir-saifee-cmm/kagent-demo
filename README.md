# kagent on wild-panda

Fresh kagent install on the `wild-panda` ephemeral vcluster (via `lava-ephemeral`),
with a Claude agent authenticated using a personal Claude Code subscription
(`CLAUDE_CODE_OAUTH_TOKEN`) instead of a metered Anthropic API key.

## Prerequisites fixed along the way

### 1. SSH defaulted to the wrong GitHub account

`git@github.com` was authenticating as a personal GitHub account instead of the
work account (`shabbir-saifee-cmm`), because a personal key added later (with
`AddKeysToAgent yes`) shadowed the work key in the ssh-agent for the plain
`github.com` host. Fixed globally in `~/.ssh/config` by pinning `Host github.com`
to `~/.ssh/id_rsa` (the work key) with `IdentitiesOnly yes`, leaving the existing
`github-personal` alias untouched for deliberate personal use.

### 2. Connected to the `wild-panda` vcluster

```bash
cd cli && go build -o lava-ephemeral .   # source build - see note below
./lava-ephemeral connect wild-panda
```

`kubectl config current-context` → `wild-panda`.

### 3. Go 1.27 TLS gets reset by a network appliance on this network

Any Go binary built with the local Go toolchain (**Go 1.27.1**) had its TCP
connections to `*.mckesson.com` / `*.eastus.aks.mckesson.com` endpoints reset
mid-request (`read: connection reset by peer`), while `curl` against the exact
same URL succeeded every time. Confirmed this is specifically about the Go
version, not auth/headers/HTTP2:

- Locally `go build`-ing the `lava-ephemeral` CLI (cli/) failed this way; the
  official prebuilt release binary (`lava-ephemeral_0.0.1_darwin_arm64` from
  GitHub Releases, built by CI with an older Go) worked immediately.
- `helm` from Homebrew (v4.3.0, Go 1.27.1) failed the same way against the
  `wild-panda` API server; `kubectl` (Go 1.26.5) and raw `curl` with the same
  mTLS client cert succeeded against the identical endpoint.
- Installing `helm` 3.20.0 (Go 1.25.6) via `asdf` fixed it completely.

This matches Go's default enablement of the post-quantum hybrid key exchange
(X25519MLKEM768) in TLS 1.3 ClientHellos in newer Go versions, which older
corporate TLS-inspection middleboxes can fail to parse and reset. `GODEBUG=tlsmlkem=0`
did **not** fix it for this specific network, so the actual fix is using an
older Go-toolchain build of the client instead of patching Go's TLS internals.

**Action taken:** `asdf plugin add helm`, `asdf install helm 3.20.0`,
`asdf set helm 3.20.0` (pins `.tool-versions` in this directory). Use
`asdf exec helm ...` (or just `helm ...` once `asdf` picks up the shim) for every
command below.

## kagent 1.x: tried it, upstream-broken, fell back to 0.x

The ask was to install **kagent 1.x** specifically. Tried it properly:

```bash
asdf exec helm install kagent-crds oci://ghcr.io/kagent-dev/kagent/helm/kagent-crds \
  --version 1.0.0-alpha5 --namespace kagent --create-namespace
asdf exec helm install kagent oci://ghcr.io/kagent-dev/kagent/helm/kagent \
  --version 1.0.0-alpha5 --namespace kagent --set providers.default=anthropic
```

The controller crash-looped:

```
substrate: dial ate-api "dns:///api.ate-system.svc:443": context deadline exceeded
```

This is a **known, open upstream bug**:
[kagent-dev/kagent#2581](https://github.com/kagent-dev/kagent/issues/2581).
The 1.x controller ("controller-v2") unconditionally dials the Agent Substrate
`ate-api` service at startup and treats failure as fatal (`log.Fatal`), even
though `controller.substrate.enabled` defaults to `false` and nothing in
values.yaml can stop the dial — the gate simply isn't wired into that code path
yet. Confirmed empirically (not assumed) across the full range of published
1.x tags — **alpha1, alpha3, and alpha5 all hit the identical crash**, with
PostgreSQL confirmed healthy first in each case to rule out a startup race.

Standing up the real Agent Substrate subsystem (`ate-system`) to satisfy the
dial was considered and rejected for now:
- It requires gVisor/microVM runtime classes on cluster nodes, which a vcluster
  cannot provide since it doesn't control the host cluster's container runtime.
- Per a maintainer comment on #2581, even a live `ate-system` hit a second,
  unresolved wall in their testing: `ate-api` expects mTLS/SPIFFE client auth,
  which the 0.x-era controller only satisfies with a plain ServiceAccountToken.

**Decision: install kagent 0.10.2 (the current stable line) instead**, since
the Claude-subscription-auth agent below is a **BYO Agent** — kagent just
deploys our container and proxies A2A to it; it doesn't touch the model auth
inside that container at all. That mechanism is identical and
controller-version-agnostic, so falling back to 0.x doesn't compromise the
actual goal.

```bash
asdf exec helm uninstall kagent -n kagent
asdf exec helm uninstall kagent-crds -n kagent

asdf exec helm install kagent-crds oci://ghcr.io/kagent-dev/kagent/helm/kagent-crds \
  --namespace kagent
asdf exec helm install kagent oci://ghcr.io/kagent-dev/kagent/helm/kagent \
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

The `*-agent.enabled=false` flags disable every bundled demo agent the chart
ships by default (k8s-agent, istio-agent, cilium-*, helm-agent, kgateway-agent,
observability-agent, promql-agent, argo-rollouts-agent) — the ask was a fresh
cluster with no pre-existing agents.

Result: `kubectl get pods -n kagent` shows only
`kagent-controller`, `kagent-ui`, `kagent-tools`, `kagent-kmcp-controller-manager`,
`kagent-grafana-mcp`, `kagent-postgresql`, all `1/1 Running`. `kubectl get agents -n kagent`
→ empty.

`providers.default=anthropic` generates one default `ModelConfig` referencing a
`kagent-anthropic` Secret we never created — harmless and unused, since the
Claude agent below doesn't go through kagent's managed-provider path at all.

## Claude agent via subscription (BYO Agent) — DONE, deployed and working

Code in `claude-byo-agent/` — custom A2A server (official `@a2a-js/sdk` +
`@anthropic-ai/claude-agent-sdk`, not the community `kagent-claude-byo-agent`
repo). Auths with `CLAUDE_CODE_OAUTH_TOKEN` (`claude setup-token`), not
`ANTHROPIC_API_KEY`, so usage bills to a personal subscription.

```bash
cd claude-byo-agent
npm install && npm run build          # sanity build
docker buildx build --platform linux/amd64 -t <registry>/claude-byo-agent:0.1.0 --provenance=false --push .
```

**Registry note:** an in-cluster registry does NOT work for this vcluster.
Tried three things, in order:
1. Deployed `registry:2` in-cluster, pushed via `kubectl port-forward` — port-forward
   drops concurrent streams (`docker push`'s parallel blob uploads fail with
   `i/o timeout`/`connection refused`); `crane push` (sequential) worked around
   that fine, but then:
2. Kubelet on the real AKS node can't resolve the vcluster's Service DNS
   (`no such host`) — pods run on the *host* cluster's nodes/DNS, not the
   vcluster's virtual one.
3. Pulling by the Service's raw ClusterIP fixed DNS, but hit the real wall:
   `http: server gave HTTP response to HTTPS client` — containerd requires
   TLS, and we have no node-level access on this managed AKS cluster to add
   an insecure-registry exception (`orca`'s Tiltfile "local registry" trick
   only works because k3d owns the node's containerd; not the case here).

**Fix: pushed to Docker Hub instead** (`shabbirsaifee/claude-byo-agent:0.1.0`)
 — real TLS, no node config needed, nodes already had internet egress.

```bash
kubectl create secret generic claude-byo-agent-oauth -n kagent \
  --from-literal=CLAUDE_CODE_OAUTH_TOKEN='<token from: claude setup-token>'

kubectl apply -f k8s/claude-byo-agent.yaml
```

All k8s manifests live in `k8s/`. `claude-byo-agent.yaml` is the `Agent` CR
(`spec.type: BYO`, image `shabbirsaifee/claude-byo-agent:0.1.0`, env
`CLAUDE_CODE_OAUTH_TOKEN` from that Secret). The Secret itself is
intentionally *not* a committed file — created imperatively so the real
token never touches git.

Verified: `kubectl get agent claude-byo-agent -n kagent` → `Ready`. Sent a
real `SendMessage` A2A JSON-RPC call through `claude-byo-agent.kagent.svc:8080`
and got back a `TASK_STATE_COMPLETED` task with a real Claude response —
full path (kagent → Service → BYO pod → Claude Agent SDK → OAuth-authenticated
subscription) confirmed working.

### Fixed: kagent's chat UI got no answer at all

kagent 0.10.x's own controller/UI calls agents without an `A2A-Version`
header. Per the A2A spec that means "treat as legacy v0.3" — but
`@a2a-js/sdk`'s server only advertised v1.0, so every real request from
kagent itself (not my manually-crafted `curl -H 'A2A-Version: 1.0'` test)
was rejected outright with `VersionNotSupportedError`, before ever reaching
the executor. Fixed in `claude-byo-agent/src/index.ts` using the SDK's own
v0.3 compat layer (`@a2a-js/sdk/compat/v0_3`):
`duplicateInterfacesForLegacy(...)` on the agent card's `supportedInterfaces`,
plus `legacyCompat: { enabled: true }` on both `agentCardHandler` and
`jsonRpcHandler`. Retested with a real legacy-shaped request (no header,
`message/send`, `kind: 'text'` parts) — works, returns a completed task with
a real Claude response.

Rebuild/redeploy after any code change:

```bash
cd claude-byo-agent
npx tsc -p tsconfig.json
docker buildx build --platform linux/amd64 -t shabbirsaifee/claude-byo-agent:0.1.0 --provenance=false --push .
kubectl rollout restart deployment/claude-byo-agent -n kagent
```
