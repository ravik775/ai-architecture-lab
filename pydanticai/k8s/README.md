# Weather Intelligence Agent — Kubernetes manifests

A direct port of `docker-compose.yml` into the `weatherapp` namespace,
built for a specific, stated goal: let the observability components
(Grafana/Prometheus/Tempo/otel-collector) scale as **separate pods**
without risking data loss, while enforcing that only `weather-app` can
write into them and everyone else gets read-only access. See
[DECISIONS.md](DECISIONS.md) for the full security model and a
decision-by-decision record of every architectural choice made building
this — context, alternatives considered, evidence, and consequences, one
entry per decision.

**External access model**: `weather-app` and Grafana are reachable from
outside the cluster, through **one shared Ingress** (not one
`LoadBalancer` Service each — see the "Why one Ingress, not two
LoadBalancers" note under Deploying). Prometheus, Tempo, otel-collector,
and litellm-proxy are internal-only by design — `kubectl port-forward` is
the documented, evidence-backed path for occasional operator/debugging
access to those, not a workaround (see "Accessing Prometheus's/Tempo's UI
without external exposure" below).

## What's here

| File | Contains |
|---|---|
| `namespace.yaml` | The `weatherapp` namespace, labeled with the Restricted Pod Security Standard |
| `network-policy.yaml` | Default-deny + explicit allow rules — the enforcement mechanism for "only weather-app writes" |
| `secrets.yaml` | **Placeholder** Secret objects — replace every value before real use |
| `configmap-*.yaml` | Verbatim ports of `litellm_config.yaml`, `docker/otel-collector-config.yaml`, `docker/prometheus.yml`, `docker/tempo.yaml`, and the Grafana provisioning/dashboard files |
| `weather-app.yaml` | Deployment (pinned to 1 replica — see below), PVC, Service |
| `litellm-proxy.yaml` | Deployment (freely scalable), Service |
| `otel-collector.yaml` | Deployment (pinned to 1 replica — see below), Service |
| `prometheus.yaml` | StatefulSet + `volumeClaimTemplates`, headless + regular Service |
| `grafana.yaml` | StatefulSet + `volumeClaimTemplates`, headless + regular Service |
| `tempo.yaml` | StatefulSet + `volumeClaimTemplates`, headless + regular Service |
| `ingress.yaml` | **The only externally-facing entry point** — one Ingress, host-based routing to `weather-app` and `grafana` |
| `kustomization.yaml` | Ties it all together for one-command apply |

Not ported: `loki` (the `optional-loki` compose profile) and the
`observability-watchdog` sidecar (a Docker-socket-based convenience script
specific to local Docker Compose — its job in Kubernetes is a
`CronJob`/liveness-probe-driven scale-to-zero pattern instead, out of
scope here). The Grafana Loki datasource entry was dropped from
`configmap-grafana-provisioning.yaml` to match.

## Communication matrix — who can talk to whom, and how

**Pull vs. push matters more than it looks like it should** — this
distinction is exactly what caused a real bug found in this project's own
security review (see [DECISIONS.md](DECISIONS.md) entry on the
`prometheus-egress` fix): a *pull* relationship means the destination
initiates the connection, so it's the **destination's egress** rule that's
needed, not the source's. Get that backwards and the `NetworkPolicy` looks
complete while actually being broken.

| Source | Destination | Port / protocol | Mode | Purpose | Enforced by (both sides required) |
|---|---|---|---|---|---|
| `weather-app` | `litellm-proxy` | TCP 4000, HTTP | Push | Agent's LLM calls — only on the agent path, never the deterministic weather path | `weather-app-egress` + `litellm-proxy-ingress` |
| `weather-app` | `otel-collector` | TCP 4318, OTLP/HTTP | Push | Trace export | `weather-app-egress` + `otel-collector-policy` |
| `prometheus` | `weather-app` | TCP 9464, HTTP | **Pull** (scrape) | Metrics collection — this *is* the only write path into Prometheus, since it's pull-based | `prometheus-egress` + `weather-app-ingress` |
| `otel-collector` | `tempo` | TCP 4317, OTLP/gRPC | Push | Tail-sampled trace storage | `otel-collector-policy` + `tempo-ingress` |
| `grafana` | `prometheus` | TCP 9090, HTTP | **Pull** (PromQL query, read-only) | Dashboards | `grafana-egress` + `prometheus-ingress` |
| `grafana` | `tempo` | TCP 3200, HTTP | **Pull** (TraceQL query, read-only) | Trace Explore view | `grafana-egress` + `tempo-ingress` |
| `ingress-nginx` (external namespace) | `weather-app` | TCP 8000, HTTP | Pull | External API/UI access | `weather-app-ingress` only — `ingress-nginx`'s own egress isn't governed by this namespace's policies at all |
| `ingress-nginx` (external namespace) | `grafana` | TCP 3000, HTTP | Pull | External dashboard access (anonymous visitors get read-only Viewer role) | `grafana-ingress` only |
| `weather-app` | Open-Meteo (internet) | TCP 443, HTTPS | Push/pull request-response | Live weather data | `weather-app-egress`'s `to: []` rule — can't be scoped by podSelector to a third party; a documented gap, see DECISIONS.md |
| `litellm-proxy` | OpenRouter (internet) | TCP 443, HTTPS | Push/pull request-response | LLM inference | `litellm-proxy-ingress`'s egress rule, same `to: []` limitation |
| All pods | CoreDNS (`kube-system`) | UDP/TCP 53 | Query | Service name resolution | `allow-dns` |
| Operator (`kubectl`) | Any pod (esp. `prometheus`/`tempo`/`otel-collector`/`litellm-proxy`) | via the Kubernetes API server | Interactive, on-demand | Debugging/analysis | Kubernetes RBAC (`pods/portforward`) — **not** `NetworkPolicy` at all; `port-forward` tunnels through the API server and never touches the pod network, so it works identically whether `NetworkPolicy` is enforced or not |

Everything not listed above is denied by `default-deny-all` — this table
*is* the complete allow-list, not a curated excerpt of it.

## Why three components are pinned to 1 replica

Not an oversight — each is a real, evidence-backed constraint carried
forward from this project's own docker-compose setup and documented
inline in the relevant manifest:

- **`weather-app`**: single-writer SQLite persistence (already documented
  in the project's main README).
- **`otel-collector`**: the `tail_sampling` processor needs every span of
  a trace on the same collector instance to decide correctly.
- **`tempo`**: local-disk trace storage cannot be shared across replicas
  in a distributed deployment (verified against Tempo's own
  storage-architecture docs — see DECISIONS.md's D6).

`prometheus` and `grafana` default to 1 replica too, but for a softer
reason — see DECISIONS.md's "Scaling without data loss, at a glance"
table for what you get and don't get if you raise those specifically.

## Prerequisites

1. **A cluster with NetworkPolicy enforcement** (Calico, Cilium, GKE
   Dataplane v2, EKS with the VPC CNI's policy add-on, etc.). On a CNI
   that doesn't enforce NetworkPolicy, `network-policy.yaml` applies
   without error but silently does nothing — verify this before relying
   on it as a real boundary.
2. **A default `StorageClass`** capable of `ReadWriteOnce` volumes, for
   the PVCs.
3. **An Ingress controller** (`ingress.yaml` assumes `ingress-nginx`;
   adjust its `ingressClassName` and `network-policy.yaml`'s
   `grafana-ingress`/`weather-app-ingress` namespaceSelectors if you use a
   different one). Verified live: `ingress-nginx` installs and works on
   Docker Desktop's Kubernetes with zero extra config — its `LoadBalancer`
   Service gets `EXTERNAL-IP: localhost` automatically (a Docker
   Desktop-specific convenience, not real cloud behavior — see the note
   under Deploying).
4. **The `weather-app` image built and reachable by your cluster.**
   `docker-compose.yml` builds it locally (`weather-intelligence-agent:local`);
   for a real cluster, build and push it to a registry your cluster can
   pull from, then update the `image:` field in `weather-app.yaml`. For a
   local cluster: `kind load docker-image weather-intelligence-agent:local`
   or `minikube image load weather-intelligence-agent:local` first.

## Deploying

```bash
# 1. Build/push the app image (see Prerequisites #4), or load it into
#    your local cluster.

# 2. Replace every placeholder in secrets.yaml with real values - do not
#    apply it as committed. See DECISIONS.md's D9 for better options than
#    hand-editing this file.

# 3. Install ingress-nginx if your cluster doesn't already have an
#    Ingress controller. Verified against this exact version live:
kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/controller-v1.15.1/deploy/static/provider/cloud/deploy.yaml
kubectl -n ingress-nginx wait --for=condition=Available deployment/ingress-nginx-controller --timeout=90s

# 3b. The ingress-nginx install creates its OWN namespace with zero Pod
#     Security enforcement - found in security review, not caught by the
#     initial install. `restricted` would break it outright (it needs the
#     NET_BIND_SERVICE capability and can't run readOnlyRootFilesystem -
#     confirmed via the project's own GitHub issue tracker, see
#     DECISIONS.md), so `baseline` is the correct level, not "leave it
#     unenforced" or "force restricted and watch it fail to start".
#     Validated live: labeled the namespace, then force-recreated the
#     controller pod to prove the label doesn't break it (PSA only checks
#     NEW pods, not already-running ones) - both succeeded.
kubectl label namespace ingress-nginx \
  pod-security.kubernetes.io/enforce=baseline \
  pod-security.kubernetes.io/enforce-version=latest \
  pod-security.kubernetes.io/audit=baseline \
  pod-security.kubernetes.io/warn=baseline
kubectl -n ingress-nginx rollout restart deployment/ingress-nginx-controller
kubectl -n ingress-nginx rollout status deployment/ingress-nginx-controller --timeout=60s
# Observed: new pod reaches 1/1 Running, 0 restarts. Confirm routing
# survived the recreation before moving on:
curl -s -H "Host: weatherapp.local" -o /dev/null -w "weather-app: HTTP %{http_code}\n" http://localhost/health/live
curl -s -H "Host: grafana.local" -o /dev/null -w "grafana:     HTTP %{http_code}\n" http://localhost/api/health
# Observed both: HTTP 200 - the label is genuinely compatible with this
# controller, not just applied and hoped for.

# 4. Point weatherapp.local and grafana.local at wherever the Ingress
#    controller's EXTERNAL-IP ends up (127.0.0.1 on Docker Desktop; a
#    real IP/hostname on a cloud cluster - use real DNS there instead of
#    a hosts-file entry):
#      kubectl -n ingress-nginx get svc ingress-nginx-controller
#    then add to your hosts file (Windows:
#    C:\Windows\System32\drivers\etc\hosts; macOS/Linux: /etc/hosts):
#      127.0.0.1  weatherapp.local grafana.local

kubectl apply -k k8s/

kubectl -n weatherapp get pods -w
```

**Why one Ingress, not two `LoadBalancer` Services** (`weather-app` and
Grafana each getting their own): a separate `LoadBalancer` Service per
app "can quickly become expensive" on a real cloud cluster since each one
provisions its own cloud load balancer, versus an Ingress Controller
letting multiple applications "share a single external IP" ([Tetrate —
Ingress Controller vs. Load
Balancer](https://tetrate.io/learn/ingress-controller-vs-load-balancer)).
Verified this actually matters even on Docker Desktop — `type:
LoadBalancer` genuinely works there (confirmed live: `EXTERNAL-IP:
localhost` in ~5s, real `HTTP 200` with zero port-forward process
running) — but that's a Docker-Desktop-only convenience, not something
that reflects real cloud-cluster cost/behavior, so building around it
would be the wrong pattern to carry forward.

**This has actually been deployed and verified against a real cluster**
(Docker Desktop's built-in Kubernetes, `v1.36.1`) — every result quoted
below, in this file and in the validation script, is from real command
output against that live deployment, not a prediction of what should
happen. Full transcript-backed detail in **DECISIONS.md**; this file has
the condensed, single-place version.

## How security is implemented here

Two independent layers — read this before the validation script below,
since the script's whole point is proving (or disproving) that each
layer actually holds, not just that the YAML exists.

**Pod level** — every container: `runAsNonRoot: true` at a specific
non-root UID (not just "not root" — an explicit UID per component: 1000
for `weather-app`/`litellm-proxy`, 10001 for `otel-collector`/`tempo`,
65534 for `prometheus`, 472 for `grafana` — matching each image's own
expected non-root user), `allowPrivilegeEscalation: false`, all Linux
capabilities dropped, `seccompProfile: RuntimeDefault`, and
`readOnlyRootFilesystem: true` with explicit `emptyDir`/PVC mounts for
the specific paths each image genuinely needs to write to. This is
**enforced at admission** by the namespace's
`pod-security.kubernetes.io/enforce: restricted` label (Pod Security
Admission) — a pod that doesn't satisfy these settings is rejected by the
API server before it's ever scheduled. Verified two ways below: the
admission rejection itself, and — since declared config isn't proof of
runtime behavior — the *actual* OS-level UID of every running process,
checked directly via `docker top` on the real containers rather than
trusted from the YAML. Zero containers run as root, confirmed live.

**Network level** — `network-policy.yaml` starts every pod at
"no ingress, no egress" (`default-deny-all`) and adds back only the
specific pod-to-pod flows this app needs (see DECISIONS.md's write-path
mapping reference and D8 for the full allow-list and the reasoning per
flow). This is **enforced by the CNI plugin**, not the Kubernetes API
server — the policy objects are
always accepted and stored regardless of whether anything reads them,
which is exactly the gap the validation script below catches.

## Security checks performed, and the guidance each one follows

Every row was checked against the live deployment (not just declared in
YAML) — "Enforced" means confirmed active; "Specified" means correctly
configured but not currently enforced on this Docker Desktop cluster (see
the `NetworkPolicy` rows in the Communication Matrix and Test Scenarios
above for why). Full context and evidence for the ones marked with a
[DECISIONS.md](DECISIONS.md) link are in that file.

| Control | Implementation | Status | Guidance it follows |
|---|---|---|---|
| Non-root execution, specific UID per component | All 6 containers | ✅ Enforced, verified via `docker top` | [Kubernetes Pod Security Standards](https://kubernetes.io/docs/concepts/security/pod-security-standards/) |
| No privilege escalation | `allowPrivilegeEscalation: false` everywhere | ✅ Enforced at admission | Same |
| All Linux capabilities dropped | `capabilities.drop: [ALL]` everywhere | ✅ Enforced at admission | Same |
| Read-only root filesystem, minimal writable exceptions | `readOnlyRootFilesystem: true` + justified `emptyDir`/PVC mounts only | ✅ Enforced, 0 restarts under it | [CIS Kubernetes Benchmark hardening baseline](https://www.plural.sh/blog/kubernetes-cis-benchmark-guide/) |
| Seccomp profile | `RuntimeDefault` everywhere | ✅ Enforced at admission | Pod Security Standards (Restricted) |
| No privileged containers / host namespaces / `hostPath` | Verified absent across all 6 pods | ✅ Confirmed absent | Pod Security Standards (Baseline+) |
| Default-deny network policy, explicit allow-list | `default-deny-all` + 11 targeted rules | 🟡 Specified correctly, **not enforced** on this cluster (no policy-capable CNI) | [Calico — default-deny best practice](https://docs.tigera.io/calico/latest/network-policy/get-started/kubernetes-default-deny) |
| Bidirectional NetworkPolicy completeness | Every pod-to-pod flow has both an egress and ingress rule | ✅ Verified complete after fixing the `prometheus-egress` gap | See [DECISIONS.md](DECISIONS.md) |
| Stateful data safe from multi-replica loss | `StatefulSet` + `volumeClaimTemplates` for Prometheus/Grafana/Tempo | ✅ Enforced, PVCs verified bound and distinct | [Kubernetes StatefulSet storage semantics](https://kubemastery.com/en/courses/cka/storage-in-statefulsets) |
| Secrets isolated per component, least scope | 3 separate `Secret` objects, no cross-component sharing | ✅ Confirmed, no real values committed | [Kubernetes Secrets management options comparison](https://infisical.com/blog/kubernetes-secrets-management) |
| Image provenance | Every image pinned to a specific version, zero `:latest` | ✅ Confirmed | General supply-chain hardening practice |
| ServiceAccount token hygiene | `automountServiceAccountToken: false` on all 6 workloads | ✅ Confirmed | Kubernetes RBAC hardening guidance |
| Ingress controller security level correctly scoped | `ingress-nginx` namespace labeled `baseline` (not `restricted` — would break it; not left unenforced) | ✅ Applied and verified — pod force-recreated under the new label, still `1/1 Running`, routing re-confirmed | [ingress-nginx: restricted PSS support issue](https://github.com/kubernetes/ingress-nginx/issues/9212) |
| External attack surface minimized | One shared Ingress, host-based routing; only 2 of 6 components ever externally reachable | ✅ Implemented | [Ingress Controller vs. LoadBalancer cost/security](https://tetrate.io/learn/ingress-controller-vs-load-balancer) |
| Login brute-force protection (Grafana) | Default protection (5-attempt lockout) left enabled | ✅ Verified live against the running container's actual config | [Grafana security best practices](https://www.mintlify.com/grafana/grafana/deployment/security/best-practices) |
| Prometheus admin API disabled | `--web.enable-admin-api` never set | ✅ Confirmed absent from container args | Prometheus operational security convention |

**One 🟡 row is still open, by design** — this document doesn't claim
everything is fixed, only what's actually true right now. The
`ingress-nginx` PSA gap is resolved (above). The remaining `NetworkPolicy`
enforcement gap is a property of this specific cluster (Docker Desktop),
not something a manifest change can fix — it needs a policy-capable CNI
installed, which is a cluster-provisioning decision, not a k8s/ file.

## Test scenarios and validation status

Every scenario actually run against a live deployment (Docker Desktop
Kubernetes, `v1.36.1`) this far — status is the real observed result, not
the expected one. Full commands for each are in the consolidated script
below; the **Command** column here is the specific one to jump to.

| # | Scenario | Layer | Status | Command |
|---|---|---|---|---|
| 1 | Pod with no `securityContext` submitted to the namespace | Pod (admission) | ✅ Rejected before creation | `kubectl run` in §2 |
| 2 | `allowPrivilegeEscalation` / capabilities / `readOnlyRootFilesystem` on all 6 running containers | Pod (declared) | ✅ Matches manifest on all 6 | `for name in ...securityContext}` loop in §2 |
| 3 | Actual runtime UID of every process (not the declared YAML) | Pod (runtime) | ✅ Non-root on all 6, confirmed directly | `docker top` loop in §2 |
| 4 | `privileged` / `hostNetwork` / `hostPID` / `hostIPC` / `hostPath` anywhere in namespace | Pod | ✅ Absent everywhere | `privileged=...hostIPC=` + `hostPath` grep, end of §2 |
| 5 | Sidecar/init containers per pod | Pod | ✅ Exactly 1 container, 0 init containers, on all 6 | `containers=...initContainers=` line, end of §2 |
| 6 | `NetworkPolicy` objects applied and stored | Network | ✅ All 10 present | `kubectl get networkpolicy` in §3 |
| 7 | CNI capable of enforcing `NetworkPolicy` present in cluster | Network | ❌ None found | `kubectl -n kube-system get pods` in §3 |
| 8 | Unlabeled same-namespace pod → `weather-app:9464` (only `prometheus` allowed) | Network | ❌ **Not enforced** — succeeded in 6.7ms | `netpol-test` in §3 |
| 9 | Unlabeled same-namespace pod → `prometheus:9090` (only `grafana` allowed) | Network | ❌ **Not enforced** — succeeded in 3.6ms | `netpol-test`, target swapped to `prometheus.weatherapp.svc.cluster.local:9090/-/healthy` — same command shape as §3, second target |
| 10 | Grafana datasources editable via UI/API | App config | ✅ `readOnly: true` on both | `curl .../api/datasources` in §5 |
| 11 | Agent path with a placeholder/invalid LLM credential | App | ✅ Fails safely — clean `HTTP 502`, no crash, no fabricated data | `curl .../v1/agent/query` in §4 |
| 12 | Weather app health, readiness (DB), deterministic REST, live Open-Meteo call, UI mount | App access | ✅ All `HTTP 200` with real data | §4 |
| 13 | Prometheus actually scraping `weather-app` (not just configured to) | Observability wiring | ✅ `"health":"up"` | §5 |

**Not tested, scope-honest**: cross-namespace traffic, the external
Ingress path (no ingress controller installed on this cluster), Secret
encryption-at-rest, image vulnerability scanning, cluster-level RBAC for
`kubectl` access itself.

## Accessing Prometheus's or Tempo's UI without external exposure

The chosen design keeps Prometheus, Tempo, otel-collector, and
litellm-proxy internal-only — `weather-app` and Grafana, via `ingress.yaml`,
are the only two components anything outside the cluster can reach at
all. `kubectl port-forward` is **the documented path for debugging/
operator access to everything else, and it should stay that way** — not
a temporary workaround waiting to be replaced by a new Ingress rule or
`LoadBalancer`. Confirmed by research, not just preference: no better
alternative exists at this project's scale (a service mesh or dev-tunnel
tool would be real new infrastructure for a problem `port-forward`
already solves), and it's a genuinely audited mechanism — every
`port-forward` request is logged in the Kubernetes API server's audit
log, unlike a raw network connection. Use it like this:

```bash
kubectl -n weatherapp port-forward svc/prometheus 9090:9090
# open http://localhost:9090 - full Prometheus web UI (graph, alerts, targets)

kubectl -n weatherapp port-forward svc/tempo 3200:3200
# Tempo has NO standalone web UI, unlike Prometheus - this only gets you
# its raw JSON query API (curl http://localhost:3200/api/search?...).
# For an actual browsable trace UI, port-forward Grafana instead and use
# its Explore view against the already-provisioned Tempo datasource:
kubectl -n weatherapp port-forward svc/grafana 3000:3000
```

**Worked example, run live against this exact deployment** — an operator
querying Prometheus's `up` metric through the port-forward, the same way
they'd use the graph tab of the web UI:

```bash
kubectl -n weatherapp port-forward svc/prometheus 19090:9090 &
curl -s 'http://localhost:19090/api/v1/query?query=up'
```

Real output:

```json
{"status":"success","data":{"resultType":"vector","result":[{"metric":{"__name__":"up","instance":"weather-app.weatherapp.svc.cluster.local:9464","job":"weather-app"},"value":[1786214875.560,"1"]}]}}
```

**Why this is the right boundary, not just a workaround**: `kubectl
port-forward` tunnels through the Kubernetes **API server** directly to
the target pod — it never touches the cluster pod network, so it's
unaffected by `NetworkPolicy` (allowed or not) and doesn't require any
Ingress, Service change, or new external exposure. Access control shifts
entirely to **Kubernetes RBAC** (who has `get`/`create` on the
`pods/portforward` subresource in this namespace) instead of network
reachability. It also means this already works today, with zero manifest
changes, regardless of whether `NetworkPolicy` itself is enforced on a
given cluster (see the gap in rows 7-9 above) — RBAC and CNI enforcement
are two independent security controls, and this path only depends on the
one that's actually guaranteed by Kubernetes itself, not by an optional
add-on.

**Security implications — read before treating this as "safe by
default"**:

- **It's exactly as strong as your RBAC, no stronger.** `port-forward`
  isn't a separately-hardened access path — anyone whose kubeconfig
  grants `pods/portforward` on this namespace can reach *any* pod's *any*
  port this way, including `weather-app` itself, bypassing every
  `NetworkPolicy` in this manifest set (enforced or not — it doesn't
  matter, this path doesn't go through the CNI at all). If your cluster's
  default RBAC is broad (Docker Desktop's default context is effectively
  cluster-admin for the local user), this affords unrestricted access to
  everything in the namespace, not just Prometheus/Tempo. Scope RBAC
  narrowly (a `Role` limited to `pods/portforward` on specific pods, not
  a blanket `cluster-admin` kubeconfig) before treating this as a real
  access boundary on a shared or production cluster.
- **The kubeconfig itself becomes a credential worth protecting.** On a
  real remote cluster, whoever holds a kubeconfig with this permission
  has the same access as the port-forward gives them — treat it like an
  SSH key or API token, not a throwaway file. On Docker Desktop
  specifically this is somewhat moot (the "cluster" is the same local
  machine, so there's no meaningful trust boundary being crossed at all)
  — but that stops being true the moment this same manifest set targets
  a real multi-user cluster.
- **It's a debugging/admin tool, not a distribution mechanism.** If
  routine, frequent access is needed by more than one or two operators,
  that's a signal to build a real internal-access path (an
  internal-only Ingress class with its own auth, a bastion, or a VPN)
  rather than distributing broad kubeconfig access to a team — this
  command is the right answer for "I, an operator with cluster access,
  need to look at something right now," not for "our team routinely uses
  this dashboard."

## Validating the deployment — all commands, one place

Run top to bottom after `kubectl apply -k k8s/`. Every command has a
comment stating what it checks and, where this exact script has already
been run against a live cluster, the **real result observed** — not the
expected one. Where those differ (step 3, NetworkPolicy), that's the
whole point of running this rather than trusting the manifest.

```bash
NS=weatherapp

# ============================================================
# 1. BASIC HEALTH — are the pods actually up?
# ============================================================
kubectl -n $NS get pods
# Observed: all 6 pods Running/Ready (weather-app, litellm-proxy,
# otel-collector, prometheus-0, grafana-0, tempo-0).

kubectl -n $NS get pvc
# Observed: all 4 PVCs Bound via the "hostpath" default StorageClass -
# confirms volumeClaimTemplates (prometheus-0/grafana-0/tempo-0) actually
# provisions a distinct volume per pod, which is the entire mechanism
# behind this manifest set's "no data loss when scaling" claim.

# ============================================================
# 2. POD-LEVEL SECURITY — is "restricted" actually enforced,
#    or just labeled?
# ============================================================

# A pod with NO security context should be REJECTED at admission, not
# just warned about. Observed live: rejected -
#   "Error from server (Forbidden): pods "pss-probe" is forbidden:
#    violates PodSecurity "restricted:latest": allowPrivilegeEscalation
#    != false ... unrestricted capabilities ... runAsNonRoot != true ...
#    seccompProfile ..."
# - and `kubectl get pod pss-probe` afterward returns NotFound: it was
# never created, not created-then-blocked.
kubectl -n $NS run pss-probe --image=busybox --restart=Never -- sleep 3600
kubectl -n $NS delete pod pss-probe --force --grace-period=0 2>/dev/null

# Confirm each RUNNING pod's declared container-level security settings
# match what's claimed above (allowPrivilegeEscalation, dropped
# capabilities, read-only root fs). Observed: identical on all 6 -
#   {"allowPrivilegeEscalation":false,"capabilities":{"drop":["ALL"]},"readOnlyRootFilesystem":true}
for name in weather-app litellm-proxy otel-collector prometheus grafana tempo; do
  echo "--- $name ---"
  kubectl -n $NS get pod -l app.kubernetes.io/name=$name \
    -o jsonpath='{.items[0].spec.containers[0].securityContext}'
  echo
done

# Confirm each pod's non-root UID as DECLARED to the API. All 6 being
# Running/Ready is itself indirect proof this is honored: Kubernetes
# refuses to START a container when runAsNonRoot:true is set and the
# image's actual UID would be 0 - a mismatch fails at container-create.
for name in weather-app litellm-proxy otel-collector prometheus grafana tempo; do
  echo "--- $name ---"
  kubectl -n $NS get pod -l app.kubernetes.io/name=$name \
    -o jsonpath='{.items[0].spec.securityContext}'
  echo
done

# DIRECT proof, not inference - the actual runtime UID of the real OS
# process, independent of what Kubernetes merely declares. kubectl exec
# doesn't work reliably on Docker Desktop's Kubernetes (a known CRI-proxy
# issue there), so this goes around it via `docker top` directly on the
# underlying containers Docker Desktop's K8s runs on the same engine.
# Observed: every single process - weather-app (1000), litellm-proxy
# (1000), otel-collector (10001), tempo (10001), prometheus (UID name
# "nobody" = 65534), grafana (472, including its own bundled
# Elasticsearch/Zipkin datasource-plugin subprocesses) - runs as its
# declared non-root UID. Zero containers run as root.
for c in weather-app litellm-proxy otel-collector tempo prometheus grafana; do
  cname=$(docker ps --filter "label=io.kubernetes.container.name=$c" \
    --filter "label=io.kubernetes.pod.namespace=$NS" --format "{{.Names}}" | head -1)
  echo "--- $c ---"
  docker top "$cname" 2>/dev/null | awk 'NR==1 || NR>1 {print $1, $NF}'
done

# No privileged containers, no host namespace sharing, anywhere in the
# namespace. Observed: every field empty/unset on all 6 pods.
kubectl -n $NS get pods -o jsonpath='{range .items[*]}{.metadata.name}{": privileged="}{.spec.containers[*].securityContext.privileged}{" hostNetwork="}{.spec.hostNetwork}{" hostPID="}{.spec.hostPID}{" hostIPC="}{.spec.hostIPC}{"\n"}{end}'

# No hostPath volumes anywhere (would bypass PVC isolation and reach the
# node's real filesystem). Observed: zero matches.
kubectl -n $NS get pods -o json | grep -o '"hostPath"' | sort | uniq -c

# Exactly one container per pod - no hidden sidecars widening the attack
# surface. Observed: 1 container, 0 initContainers, on all 6.
kubectl -n $NS get pods -o jsonpath='{range .items[*]}{.metadata.name}{": containers="}{.spec.containers[*].name}{" initContainers="}{.spec.initContainers[*].name}{"\n"}{end}'

# ============================================================
# 3. NETWORK-LEVEL SECURITY — are the NetworkPolicy objects
#    actually enforced, or just stored?
# ============================================================
kubectl -n $NS get networkpolicy
# Observed: all 11 objects present (default-deny-all, allow-dns,
# weather-app-egress/-ingress, litellm-proxy-ingress,
# otel-collector-policy, tempo-ingress, prometheus-ingress/-egress,
# grafana-ingress/-egress). prometheus-egress was added after a security
# review found weather-app-ingress's inbound rule had no matching
# outbound rule on the prometheus side - see DECISIONS.md.

# Every pod-to-pod flow needs BOTH an egress rule on the source and an
# ingress rule on the destination - this is how the prometheus-egress
# gap was actually found (a targeted describe on each policy, cross-
# checked against the Communication Matrix above for a missing pair):
kubectl -n $NS describe networkpolicy prometheus-egress prometheus-ingress

# Is the ingress-nginx namespace (outside $NS, not covered by anything
# above) actually enforcing anything on its own pods?
kubectl get namespace ingress-nginx --show-labels
# Observed: pod-security.kubernetes.io/enforce=baseline (applied after a
# security review found this namespace had NO enforcement at all -
# restricted would break ingress-nginx outright, baseline is the
# evidence-backed correct level - see DECISIONS.md).

# Does this cluster even have a CNI capable of enforcing NetworkPolicy?
kubectl -n kube-system get pods
# Observed on Docker Desktop: coredns, etcd, kube-apiserver,
# kube-controller-manager, kube-proxy, kube-scheduler,
# storage-provisioner, vpnkit-controller. NO Calico/Cilium/Flannel pod -
# no policy-enforcing CNI is running at all.

# The actual test: an UNLABELED pod tries to reach weather-app's metrics
# port, which weather-app-ingress restricts to the prometheus-labeled pod
# only. Needs an explicit security context to pass Pod Security Admission
# (see #2) before NetworkPolicy even gets a chance to matter.
kubectl -n $NS run netpol-test --restart=Never --image=curlimages/curl:latest \
  --overrides='{"spec":{"securityContext":{"runAsNonRoot":true,"runAsUser":1000,"runAsGroup":1000,"seccompProfile":{"type":"RuntimeDefault"}},"containers":[{"name":"netpol-test","image":"curlimages/curl:latest","command":["curl","-m","8","-s","-o","/dev/null","-w","HTTP_STATUS=%{http_code} TIME=%{time_total}s\n","http://weather-app.weatherapp.svc.cluster.local:9464/metrics"],"securityContext":{"allowPrivilegeEscalation":false,"capabilities":{"drop":["ALL"]}}}]}}'
sleep 12
kubectl -n $NS logs netpol-test
# Observed on Docker Desktop: "HTTP_STATUS=200 TIME=0.006681s" - the
# request SUCCEEDED in 6.7ms. This is a real, confirmed gap on this
# specific cluster, not a hypothetical: the policy exists and is stored
# correctly (step above), but nothing on Docker Desktop consults it. See
# DECISIONS.md's D8 for why (no CNI network-policy controller) and the
# fix (install Calico/Cilium). On a cluster WITH a policy-enforcing CNI,
# this command should instead time out after 8s with no response.
kubectl -n $NS delete pod netpol-test --force --grace-period=0

# Second, independent target: an unlabeled pod against prometheus-ingress
# (allows only the grafana-labeled pod on :9090) - confirms the gap is
# systemic across the whole policy set, not one-off on a single rule.
kubectl -n $NS run netpol-test-2 --restart=Never --image=curlimages/curl:latest \
  --overrides='{"spec":{"securityContext":{"runAsNonRoot":true,"runAsUser":1000,"runAsGroup":1000,"seccompProfile":{"type":"RuntimeDefault"}},"containers":[{"name":"netpol-test-2","image":"curlimages/curl:latest","command":["curl","-m","8","-s","-o","/dev/null","-w","HTTP_STATUS=%{http_code} TIME=%{time_total}s\n","http://prometheus.weatherapp.svc.cluster.local:9090/-/healthy"],"securityContext":{"allowPrivilegeEscalation":false,"capabilities":{"drop":["ALL"]}}}]}}'
sleep 12
kubectl -n $NS logs netpol-test-2
# Observed on Docker Desktop: "HTTP_STATUS=200 TIME=0.003595s" - same
# result, different target/policy. Confirms this isn't specific to
# weather-app-ingress.
kubectl -n $NS delete pod netpol-test-2 --force --grace-period=0

# ============================================================
# 4. APPLICATION ACCESS — does the app actually work end to end?
# ============================================================
kubectl -n $NS port-forward svc/weather-app 18000:8000 &
sleep 3

# Liveness - observed: {"status":"ok"} / HTTP 200
curl -s -w "\nHTTP %{http_code}\n" http://localhost:18000/health/live

# Readiness (confirms live DB connectivity on the mounted PVC) -
# observed: {"status":"ready"} / HTTP 200
curl -s -w "\nHTTP %{http_code}\n" http://localhost:18000/health/ready

# Deterministic REST path, no LLM involved - observed: real country list,
# HTTP 200 (IN/LI/CH/US, matching the seeded location hierarchy)
curl -s -w "\nHTTP %{http_code}\n" http://localhost:18000/v1/locations/countries

# Deterministic weather path with a REAL live call to Open-Meteo (not
# cached, not mocked) - observed: HTTP 200, real Hyderabad conditions
# ("temperature_c":23.2, "cache_status":"miss", "latency_ms":886) -
# confirms outbound internet egress from the pod genuinely works.
curl -s -w "\nHTTP %{http_code}\n" "http://localhost:18000/v1/weather/current?location_id=hyderabad"

# NiceGUI UI mount - observed: HTTP 200 after following the 307 redirect,
# 27621 bytes, <title>Weather Intelligence Agent</title> - confirms the
# UI mounted correctly (this is also an implicit regression check for the
# /app/.nicegui write-permission bug this project hit once before - see
# the main README's troubleshooting section).
curl -s -L -w "\nHTTP %{http_code}\n" http://localhost:18000/ui/ -o /tmp/ui.html
grep -o "<title>[^<]*</title>" /tmp/ui.html

# Agent path - THIS IS EXPECTED TO FAIL on a fresh apply, honestly:
# secrets.yaml ships OPENROUTER_API_KEY as the literal placeholder
# "replace_me". Observed: {"detail":"Agent failed to produce a
# response"} / HTTP 502 - the app is doing exactly the right thing here
# (a clean, typed 502, not a crash or a fabricated answer). Replace the
# secret with a real key (see Deploying step 2) to actually exercise this
# path.
curl -s -w "\nHTTP %{http_code}\n" -X POST http://localhost:18000/v1/agent/query \
  -H "Content-Type: application/json" \
  -d '{"message": "What is the weather in Hyderabad?"}' --max-time 30

kill %1 2>/dev/null

# ============================================================
# 5. OBSERVABILITY WIRING — is Prometheus/Grafana actually connected,
#    not just running?
# ============================================================
kubectl -n $NS port-forward svc/prometheus 19090:9090 &
sleep 3
curl -s 'http://localhost:19090/api/v1/targets?state=active'
# Observed: weather-app target present, "health":"up", scraping
# http://weather-app.weatherapp.svc.cluster.local:9464/metrics on
# schedule - it's genuinely scraping, not just configured to.
kill %1 2>/dev/null

kubectl -n $NS port-forward svc/grafana 13000:3000 &
sleep 3
curl -s http://localhost:13000/api/health
# Observed: {"database":"ok","version":"13.1.2",...}
curl -s http://localhost:13000/api/datasources
# Observed: both Prometheus and Tempo present, each with "readOnly":true
# (from editable:false in the provisioning ConfigMap) - confirms the
# "no one edits datasources, they're code" intent is actually in effect,
# not just configured.
kill %1 2>/dev/null
```

## Scaling something later

- `litellm-proxy`: `kubectl -n weatherapp scale deployment/litellm-proxy --replicas=3` — safe, no caveats.
- `prometheus` / `grafana` / `tempo`: bumping `replicas:` on the
  StatefulSet is *safe from data loss* (each new pod gets its own PVC
  automatically) but does not give you one coherent scaled-out service —
  read DECISIONS.md's "Scaling without data loss, at a glance" table before doing
  this so the trade-off is a decision, not a surprise.
