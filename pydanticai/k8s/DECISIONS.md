# Architecture & Security Decision Log

This is both the decision record and the security model for `k8s/` —
merged deliberately, because they were never really two separate things:
almost every decision below *is* a security decision (who can reach what,
what runs with what privilege, what happens if a replica count changes).
Keeping them in one file matches this project's "concepts, not
complication" goal better than two overlapping documents did.

**Format**: the TOGAF-aligned discipline of capturing **Context →
Decision → Alternatives Considered → Evidence → Consequences** for each
choice, kept deliberately proportionate to this project's scope rather
than the full TOGAF ADM ceremony (no separate Business/Data/Application/
Technology Architecture documents — this is one deployment, not an
enterprise portfolio). The numbered decisions (D1–D16) are ordered
chronologically, as they were actually made; two reference sections
follow them (per-component write-path mapping, and what's explicitly out
of scope) since those aren't decisions so much as ways of reading the
decisions above.

Every "Evidence" line is either a live command run against this exact
deployment, or a cited external source checked at decision time — nothing
here is asserted from memory alone.

---

## Reference: how "only weather-app writes" maps per component

The project's core requirement doesn't map onto every component the same
way, because not every component has a "write API" in the first place —
worth being precise about, since the literal phrase doesn't translate
1:1. This reference sits outside the numbered decisions below because
it's a *reading* of several of them (D8, D11, D15) together, not a
decision on its own:

- **Prometheus is pull-based.** Nothing "pushes" metrics into it —
  Prometheus scrapes `weather-app:9464/metrics` on its own schedule
  (`configmap-prometheus.yaml`). So "only weather-app writes to
  Prometheus" is enforced by the scrape config only ever targeting
  `weather-app`, and by `prometheus-egress` + `weather-app-ingress`
  together (D15) restricting who that scrape connection can even reach.
  Nothing can push into it at all, either — `--web.enable-admin-api` (the
  flag that would expose delete/snapshot endpoints) is deliberately never
  set.
- **Tempo receives traces via OTLP push from `otel-collector` only** —
  enforced by `tempo-ingress`, which allows only the `otel-collector` pod
  on port 4317. `weather-app` itself never talks to Tempo directly.
- **Grafana has no write path from the app at all** — it's a pure
  consumer of Prometheus/Tempo as read-only datasources (a PromQL/TraceQL
  query client has no write semantics against those APIs regardless of
  network reachability). What "no one except the app writes" means for
  Grafana specifically: dashboards are ConfigMap-provisioned as code,
  with `allowUiUpdates: false` in the provisioning config, so a human
  editing through the UI can't make a change that survives a
  provisioning reload — and anonymous/external viewers get the Viewer org
  role, which cannot create, edit, or delete anything.
- **`weather-app` itself is now also a read target from outside the
  cluster** (D11) — this doesn't change any of the above; the Ingress
  route to `weather-app` serves its own API/UI, an entirely separate
  concern from whether anything can write into the observability stack.

---

## D1 — StatefulSet + `volumeClaimTemplates` for Prometheus, Grafana, Tempo

**Context**: the brief required these three to run as separate,
independently-scalable pods without risking data loss if replicas
change.

**Decision**: `StatefulSet` with `volumeClaimTemplates`, not `Deployment`
with a shared PVC.

**Alternatives considered**: a `Deployment` with one shared PVC (rejected
— `ReadWriteOnce` means only one pod can mount it, and a second replica
would either fail to start or corrupt the first's data); a `Deployment`
with no persistent storage at all (rejected — loses all data on pod
restart, defeats the stated goal).

**Evidence**: Kubernetes' own StatefulSet storage semantics — each
replica gets its own automatically-provisioned PVC, and scaling down does
not delete existing PVCs (data retained, not lost). [Kubernetes
StatefulSet storage guide](https://kubemastery.com/en/courses/cka/storage-in-statefulsets).
Verified live: all 4 PVCs (`weather-app-data`, `data-prometheus-0`,
`data-grafana-0`, `data-tempo-0`) bound automatically via the cluster's
default `StorageClass` on first apply.

**Consequences**: correct, safe default. Does *not* by itself give
coherent multi-replica behavior — see D4 and D5 for what scaling these
past 1 replica actually buys you.

---

## D2 — `weather-app` stays a `Deployment`, pinned to 1 replica

**Context**: `weather-app` also has local state (a SQLite file on a PVC).

**Decision**: `Deployment`, not `StatefulSet`, with `replicas: 1`
explicit (not left to default) and `strategy: Recreate` instead of
`RollingUpdate`.

**Alternatives considered**: `StatefulSet` (rejected — no need for stable
per-pod network identity or ordered rollout, just one consistently
attached volume, which a 1-replica `Deployment` + PVC already gives).

**Evidence**: this constraint is carried forward from the main project's
own documented architecture (SQLite is single-writer — see the main
repo's README, "Known limitations"), not a new finding.
`strategy: Recreate` matters specifically because a `RollingUpdate` would
briefly run old and new pods concurrently, both trying to attach the same
`ReadWriteOnce` PVC.

**Consequences**: scaling `weather-app` requires migrating off SQLite
first (documented, not built — same posture as the rest of this
project).

---

## D3 — `otel-collector` stays a `Deployment`, pinned to 1 replica

**Context**: the `tail_sampling` processor buffers spans per trace ID
before deciding what to keep.

**Decision**: `replicas: 1`, explicit.

**Evidence**: `tail_sampling` requires every span of a given trace to
land on the *same* collector instance to decide correctly — carried
forward from the main project's own documented constraint, not a new
finding. Scaling without a trace-ID-aware load balancer in front would
silently (not loudly) break the "always keep failed-request traces"
guarantee.

**Consequences**: a load-balancing exporter in front of >1 collector
replica is the documented, not-built, scale-out path.

---

## D4 — Prometheus HA pattern: independent replicas + Thanos (documented, not built)

**Context**: could `prometheus.yaml`'s `replicas:` just be raised for
"scaling"?

**Decision**: default stays `replicas: 1`. If raised, each replica is
safe from data loss (D1) but is a fully independent, non-deduplicated
copy of the same data — not sharded, not coherent.

**Alternatives considered**: a sharded/federated Prometheus setup
(rejected as premature — no measured requirement); building Thanos now
(rejected — real new infrastructure for a demo-scope app).

**Evidence**: Prometheus has no native sharded-write mode; the documented
HA pattern is running independent replica pairs and deduplicating *at
query time*, typically via Thanos Query and a replica label. [Prometheus
HA via independent replicas](https://last9.io/blog/high-availability-in-prometheus/).

**Consequences**: honestly labeled trade-off, not silently hidden — see
the "Scaling without data loss, at a glance" table near the end of this
file for the explicit "what you get / don't get" statement.

---

## D5 — Grafana HA requires an external DB (documented, not built)

**Context**: same question as D4, for Grafana.

**Decision**: default `replicas: 1`. Raising it would produce N
*divergent* instances (each with its own local SQLite state), not one
coherent service.

**Evidence**: Grafana's own official HA documentation requires migrating
its state to an external Postgres/MySQL (plus Redis/Memcached for
session cache) before multiple replicas behave coherently. [Grafana — Set
up for high availability](https://grafana.com/docs/grafana/latest/setup-grafana/set-up-for-high-availability/).

**Consequences**: a real, separate stateful service (Postgres) would need
to be added for genuine Grafana HA — not built, for the same "no measured
requirement yet" reasoning as SQLite-vs-Postgres for `weather-app`
itself.

---

## D6 — Tempo: local storage is a hard scaling ceiling, not a soft trade-off

**Context**: `docker/tempo.yaml` (ported verbatim into `configmap-tempo.yaml`)
uses local-disk storage.

**Decision**: `replicas: 1`, and explicitly documented as **not**
safely raisable at all without a storage backend change first — different
in kind from D4/D5's "safe but divergent" framing.

**Evidence**: Tempo's own architecture documentation states a local
storage backend *cannot* be shared across replicas in a distributed
deployment at all — traces written to one replica are invisible to
queries hitting another. [Grafana Tempo — Plan your
deployment](https://grafana.com/docs/tempo/latest/set-up-for-tracing/setup-tempo/plan/).

**Consequences**: object storage (S3/GCS/Azure Blob) in
`configmap-tempo.yaml`'s `storage.trace.backend` is required before this
ceiling can be lifted — not a config flag, a real architecture change.

---

## D7 — Pod Security Standard: `restricted` for the `weatherapp` namespace

**Context**: the brief required pod-level hardening.

**Decision**: label the namespace `pod-security.kubernetes.io/enforce: restricted`,
and configure every container to actually satisfy it (`runAsNonRoot` at
a specific per-component UID, `allowPrivilegeEscalation: false`, all
capabilities dropped, `seccompProfile: RuntimeDefault`,
`readOnlyRootFilesystem: true` with minimal justified writable mounts).

**Alternatives considered**: `baseline` (rejected as the *default* for
this namespace — `restricted` is achievable for every one of the 6
workloads here with no functional loss, verified live); a custom
admission webhook / OPA Gatekeeper policy (rejected — Pod Security
Admission already covers everything needed here natively, extra tooling
would be unjustified complexity for a single namespace).

**Evidence**: Pod Security Admission is the current, non-deprecated
successor to PodSecurityPolicy (removed in Kubernetes 1.25); `restricted`
is the most stringent standard profile. [Kubernetes — Enforcing Pod
Security Standards](https://kubernetes.io/docs/setup/best-practices/enforcing-pod-security-standards/).
Verified live, twice: (1) a bare pod with no security context is rejected
at admission, never created; (2) `docker top` on all 6 running containers
confirms every process runs at its declared non-root UID, not just that
the config claims it.

**Consequences**: `ingress-nginx`, installed later (D16), needed its own,
different decision — it cannot run under `restricted` at all.

---

## D8 — `NetworkPolicy`: default-deny plus explicit allow-list

**Context**: the brief required "only weather-app writes... everyone
else read-only," even for same-namespace traffic.

**Decision**: `default-deny-all` (deny everything) + `allow-dns` +
one targeted policy per real pod-to-pod flow — 11 objects in total after
D15's fix.

**Alternatives considered**: policies scoped only to specific "risky"
flows, leaving everything else implicitly allowed (rejected — the
starting assumption in Kubernetes is allow-everything absent a policy, so
this doesn't establish least-privilege, it just documents intent).

**Evidence**: default-deny-first is the standard zero-trust pattern for
namespace isolation — without it, traffic not explicitly denied is
implicitly allowed. [Calico — default-deny best
practice](https://docs.tigera.io/calico/latest/network-policy/get-started/kubernetes-default-deny).

**Consequences**: only as strong as the cluster's CNI (see D9's sibling
finding on enforcement) — the policy objects are always accepted and
stored by the API server regardless of whether any CNI actually reads
them. Verified live on Docker Desktop: it doesn't (no policy-capable CNI
present in `kube-system`).

---

## D9 — Secrets: native `Secret` objects now, Sealed Secrets recommended next

**Context**: the brief asked for documented options, not necessarily the
most sophisticated implementation.

**Decision**: native Kubernetes `Secret` objects (`secrets.yaml`, shipped
with placeholder values only), matching this project's existing
`.env`-file demo-grade posture.

**Alternatives considered and researched**: Sealed Secrets (asymmetric
encryption, safe to commit to git — the best fit for this specific
git-committed manifest repo, recommended as the next step, not built
now); External Secrets Operator (best when already using a cloud secret
manager — not applicable here); HashiCorp Vault (most powerful — dynamic,
short-TTL credentials — but real operational overhead disproportionate to
three `Secret` objects at this scope).

**Evidence**: comparison of native Secrets (base64, not encrypted, needs
etcd KMS envelope encryption for real protection), Sealed Secrets, ESO,
and Vault, with Sealed Secrets specifically noted as GitOps-friendly.
[Kubernetes Secrets Management in 2026 —
comparison](https://infisical.com/blog/kubernetes-secrets-management).

**Consequences**: `secrets.yaml` must never be applied with real values
committed to git — documented explicitly in the file's own header
comment.

---

## D10 — Prometheus scrape config: static target, not Kubernetes service discovery

**Context**: could Prometheus auto-discover `weather-app` via
`kubernetes_sd_configs` instead of a fixed target?

**Decision**: static target
(`weather-app.weatherapp.svc.cluster.local:9464`), matching the existing
`docker/prometheus.yml` pattern.

**Alternatives considered**: `kubernetes_sd_configs` (rejected — requires
granting Prometheus a `ClusterRole` to list/watch pods, services, and
endpoints *cluster-wide*, a real privilege-footprint increase for what is
currently exactly one scrape target).

**Evidence**: this was a direct user decision point at the time (not
solely a unilateral choice) — offered both options with the RBAC
trade-off stated, static config was chosen.

**Consequences**: adding a second scrape target later means editing the
ConfigMap by hand, not automatic discovery. Acceptable at this project's
scale; revisit if the number of scrapeable services grows.

---

## D11 — One shared `Ingress`, not two `LoadBalancer` Services

**Context**: `weather-app` and Grafana both needed external access.

**Decision**: one `Ingress` (`ingress.yaml`), host-based routing,
fronted by one `ingress-nginx` controller (itself backed by one
`LoadBalancer`).

**Alternatives considered**: a separate `type: LoadBalancer` Service per
app (this was the initially-requested approach — changed after research,
with the user's explicit sign-off on the alternative); `NodePort` per app
(rejected — every node becomes an entry point, wider exposure than
`LoadBalancer`).

**Evidence**: a separate `LoadBalancer` Service per app provisions a
separate cloud load balancer per app on a real cluster — "can quickly
become expensive... especially in microservices environments," versus an
Ingress Controller letting multiple applications "share a single external
IP." [Ingress Controller vs. Load
Balancer](https://tetrate.io/learn/ingress-controller-vs-load-balancer).
Between `NodePort` and `LoadBalancer` specifically, `LoadBalancer` lets
"provider-managed firewalls... filter traffic before it reaches cluster
nodes," a narrower exposure surface than `NodePort`. [LoadBalancer vs
NodePort](https://www.groundcover.com/learn/networking/loadbalancer-vs-nodeport).

**Consequences**: needed a real `NetworkPolicy` change (a new allow rule
on `weather-app-ingress` for the `ingress-nginx` namespace) and a real
Ingress controller to actually be installed — both done and verified
live (D16 is the security follow-up this surfaced).

---

## D12 — `kubectl port-forward` retained as the permanent path for internal-only components

**Context**: with `weather-app`/Grafana now externally reachable, should
Prometheus/Tempo get the same treatment for convenience?

**Decision**: no — Prometheus, Tempo, otel-collector, and litellm-proxy
stay internal-only, permanently, with `port-forward` as the documented
operator-access path, not a stopgap awaiting a "real" solution.

**Alternatives researched**: a service mesh (Istio/Linkerd) for
fine-grained internal access control (rejected — real new infrastructure
for a problem already solved at this scale); local-dev traffic
interception tools (mirrord/Telepresence-style) (rejected — those solve
"run my code against cluster services," a different problem than
"an operator wants to look at a dashboard").

**Evidence**: no better-fitting alternative was found for this project's
scale; `port-forward` is a legitimate, audited mechanism — every request
is logged in the Kubernetes API server's audit log. [Kubernetes Port
Forwarding Guide](https://www.plural.sh/blog/kubernetes-port-forward-guide/).
It also structurally doesn't touch the pod network at all (tunnels
through the API server directly), so it's unaffected by whether
`NetworkPolicy` is enforced (D8) either way.

**Consequences**: access control for these four components rests
entirely on Kubernetes RBAC (`pods/portforward`), not network
reachability — documented explicitly in README.md's security-implications
note, including that this is only as strong as how narrowly that RBAC is
scoped.

---

## D13 — Ingress routing: host-based, not path-based

**Context**: `weather-app` and Grafana share one Ingress (D11) — how do
requests get routed to the right one?

**Decision**: host-based (`weatherapp.local` / `grafana.local`), not
path-based (`/` vs. `/grafana`).

**Alternatives considered**: path-based routing (rejected — Grafana would
need `GF_SERVER_SERVE_FROM_SUB_PATH` wired up specifically to work
correctly under a non-root path, a real app-side config dependency;
host-based needs zero app-side changes to either component).

**Evidence**: host-based routing is also the pattern real DNS would use
in production (`app.example.com` / `grafana.example.com`) — a path-prefix
scheme only makes sense as a single-domain local convenience, not
something to build the "real" pattern around.

**Consequences**: local testing needs a hosts-file entry (documented in
README.md); a real cluster needs actual DNS records instead — the
`Ingress` resource itself doesn't change either way.

---

## D14 — TLS deliberately deferred

**Context**: `ingress.yaml` initially included a `tls:` block referencing
a certificate secret that didn't exist.

**Decision**: removed for now — plain HTTP, with `ssl-redirect` **not**
enabled (enabling it without a real certificate would 301-redirect every
request to an endpoint serving nothing).

**Evidence**: this is a self-correction caught during the same work
session, not an external finding — matches the main project's existing,
already-documented "no TLS without a real cert, terminate at a reverse
proxy" stance.

**Consequences**: a real certificate (cert-manager, or a manually
provisioned one) is a stated prerequisite before this moves beyond local
testing — documented as a TODO comment directly in `ingress.yaml`, not
silently left out.

---

## D15 — Fixed: `prometheus` had no egress rule to scrape `weather-app`

**Context**: a full security review of `network-policy.yaml`, checking
every pod-to-pod relationship for both an egress rule on the source and
an ingress rule on the destination.

**Finding**: `weather-app-ingress` correctly allowed the *inbound* half
of Prometheus's scrape connection, but `prometheus.yaml` had no matching
egress rule permitting Prometheus to *originate* that connection.
Prometheus scrapes — meaning it initiates the connection — so this is the
source's egress that was missing, not the destination's ingress.

**Decision**: added `prometheus-egress`, allowing `prometheus` →
`weather-app:9464`.

**Evidence**: this was found by systematically pairing every flow in the
Communication Matrix against its two required rules, not by testing
(testing couldn't have caught it — `NetworkPolicy` isn't enforced on
this cluster at all, so the bug was invisible to every live functional
test run so far). Verified the fix: re-rendered
(`kubectl kustomize`), re-applied, `prometheus-egress` confirmed created
and correctly formed via `kubectl describe`, and Prometheus's scrape
target re-confirmed `"health":"up"` afterward.

**Consequences**: this is the single most important finding in the whole
security review — a policy set that *looks* complete (10 objects, one per
component) but would have silently broken core metrics collection the
moment `NetworkPolicy` enforcement was actually turned on, which is
exactly the fix this project's own documentation recommends doing next.

---

## D16 — Fixed: `ingress-nginx`'s own namespace had zero Pod Security enforcement

**Context**: same security review, extended to the `ingress-nginx`
namespace created by its own install (D11) — outside `weatherapp`, so not
covered by D7's label at all.

**Finding**: `kubectl get namespace ingress-nginx --show-labels` showed
no `pod-security.kubernetes.io/*` label whatsoever. The controller pod
happened to already run reasonably hardened by its own upstream defaults
(non-root, capabilities mostly dropped) — but nothing was *enforcing*
that; it was just the current default.

**Decision**: label the `ingress-nginx` namespace `baseline`, not
`restricted` and not left unenforced.

**Alternatives considered**: `restricted` (rejected — would break the
controller outright); leaving it unenforced (rejected — that's the
gap being fixed).

**Evidence**: the ingress-nginx project's own issue tracker confirms
`restricted` causes deploy failure — it needs the `NET_BIND_SERVICE`
capability addition (disallowed under `restricted`) and cannot run
`readOnlyRootFilesystem: true` without crashing on certificate-file
creation. [ingress-nginx: restricted PSS support
issue](https://github.com/kubernetes/ingress-nginx/issues/9212).

**Consequences**: verified live, not just applied and assumed — force-
recreated the controller pod after labeling (`rollout restart`) to prove
`baseline` doesn't break it, since Pod Security Admission only checks
pods at creation time, not retroactively. New pod reached `1/1 Running`,
0 restarts, and both `weatherapp.local`/`grafana.local` routing
re-confirmed working afterward.

---

## Reference: scaling without data loss, at a glance

The full evidence and reasoning for each of these is in D1/D4/D5/D6
above — this table is only the punchline, for whoever wants the answer
without re-reading four decision entries.

| Component | Safe to run >1 replica? | What you actually get |
|---|---|---|
| `prometheus` | Yes, no data loss (D1) | N independent, slightly divergent copies — not one coherent store. Thanos Query is the documented next step for a unified view (D4), not built. |
| `grafana` | Yes, no data loss (D1) | N *divergent* instances (separate local state each) — not an HA pair, until an external Postgres/MySQL is added (D5), not built. |
| `tempo` | **No** — hard ceiling, not a soft trade-off (D6) | Local-disk storage cannot be shared across replicas at all; traces on one replica are invisible to queries on another. Object storage (S3/GCS/Azure Blob) is required first. |
| `weather-app` | No | Single-writer SQLite (D2) — a Postgres migration is the documented path, not built. |
| `otel-collector` | No, without extra work | `tail_sampling` needs every span of a trace on one instance (D3) — needs a trace-ID-aware load balancer in front first. |
| `litellm-proxy` | **Yes, freely** | The one genuinely stateless component in this manifest set — no caveats. |

## Explicitly out of scope (stated, not hidden)

Things a production rollout would need that this deployment deliberately
doesn't build, because none have a demonstrated requirement at this
project's scope — consistent with the "start simple, document the swap
point" posture applied everywhere else in this project (SQLite vs.
Postgres, in-memory cache vs. Redis, etc.):

- **No mTLS between pods.** All intra-namespace traffic is plaintext
  HTTP/OTLP. A service mesh (Istio, Linkerd) or Cilium's transparent
  encryption would close this. Lower-stakes than it sounds: this is
  internal-only traffic behind the `NetworkPolicy` boundary (D8), not the
  app's own public-facing TLS gap (D14), which is the one that actually
  matters most before any real exposure.
- **No admission policy engine** (OPA Gatekeeper, Kyverno) beyond what
  Pod Security Admission's `restricted`/`baseline` labels (D7, D16)
  already cover. PSA is genuinely sufficient for container-level settings
  at single-namespace scale; an admission engine matters more for
  organization-wide rules (image registry allow-lists, mandatory limits
  across many teams) that don't apply here.
- **No image scanning or provenance verification** wired into a deploy
  pipeline. Images are pinned to specific versions (no `:latest`), but
  nothing verifies signatures or scans for CVEs before deploy.
  Trivy/Grype in CI, or a signing policy via Sigstore/cosign, would be
  the next step for a real pipeline.
- **No cluster-level RBAC for who can `kubectl` into this namespace at
  all.** Everything above covers what runs *inside* the namespace, not
  who has operator access to the cluster itself — that's a
  `Role`/`RoleBinding` concern outside this manifest set's scope, and
  directly relevant to D12's point about `port-forward` only being as
  safe as the RBAC around it.
