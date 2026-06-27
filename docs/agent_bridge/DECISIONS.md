# Decisions (ADRs) — AI Agent → ChatGPT API Bridge

> Status: **Proposed** for all. Grounded in repository evidence on
> 2026-06-27.

---

## ADR-AGENT-001: Hybrid synchronous + asynchronous API

Status: Proposed

### Context

The bridge is request/response oriented (`CLAUDE.md` §7). Agents/workflow
systems retry automatically and need durable, restart-safe, idempotent
submission. The existing synchronous OpenAI-shaped routes must stay
unchanged for compatibility (`docs/ARCHITECTURE.md`, `CLAUDE.md` §14).

### Decision

**Option C — Hybrid.** Keep all existing `/v1/*` synchronous routes
unchanged; add a **new, additive** `/v1/agent/*` durable job API.

### Alternatives Considered

- **A — extend `/v1` only:** rejected — synchronous request/response cannot
  give agents restart-safe retrieval or idempotency for 90-minute research
  jobs.
- **B — async-only:** rejected — breaks existing clients, the character-game
  integration, and the OpenAI-shaped contract.

### Consequences

- Two API surfaces to document/test; clear separation required.
- More surface area, but no backward-compat risk.

### Validation Required

- Existing sync routes + tests unchanged after Phase 1.
- Agent routes produce durable, restart-recoverable jobs.

---

## ADR-AGENT-002: SQLite-backed Phase 1 persistence

Status: Proposed

### Context

`BridgeAdminStore` already uses stdlib `sqlite3` with an inline idempotent
`_migrate()` (`admin_store.py:27`), no migration framework (`CLAUDE.md`
§11). The repo minimizes dependencies (`CLAUDE.md` §10).

### Decision

Persist `agent_jobs`/`job_results`/`job_events`/`job_attempts` in the same
SQLite admin DB, extending `_migrate()` additively.

### Alternatives Considered

- PostgreSQL: rejected for Phase 1 — no relational-scale/distributed need
  yet; adds an external dependency and ops burden.

### Consequences

- Single-file metadata, easy backup; SQLite write-lock under high
  concurrency could contend (monitor; migrate per `STORAGE_DESIGN.md`
  thresholds).

### Validation Required

- Schema idempotent; compare-and-swap transitions race-free under tests.

---

## ADR-AGENT-003: Local filesystem Phase 1 artifact/input storage

Status: Proposed

### Context

Generated images/research already live in `outputs/chatgpt-images/`/
`outputs/chatgpt-research/` + the `artifacts` table with a working
download path (`/v1/chatgpt/files/{file_id}/{filename}`).

### Decision

Store binaries/large text on the local filesystem under
`outputs/agent-jobs/<job_id>/`; reuse the `artifacts` table (add nullable
`job_id`) so the existing download path works unchanged.

### Alternatives Considered

- S3/MinIO from day one: rejected — no multi-host need yet.

### Consequences

- Single-host only until a storage adapter is added (Phase 4).

### Validation Required

- Path-traversal-safe (opaque IDs); atomic writes; orphan/missing-file
  reconciliation.

---

## ADR-AGENT-004: Reuse existing provider, router, and concurrency

Status: Proposed

### Context

`ChatGPTProvider`, `AccountRouter` (`openai_compat.py:80`), and
`BoundedSemaphore` limiters (`:225`, `:228`) already implement the hard
parts (transport, routing, throttling, preflight quota).

### Decision

The coordinator calls the same provider/router/limiter path as the sync
routes. No transport redesign.

### Alternatives Considered

- A parallel provider path for jobs: rejected — duplicates quirks, drifts
  from sync behavior.

### Consequences

- Jobs inherit all current provider limitations (capture expiry, hidden
  burst limits, zero token usage).

### Validation Required

- A job and a sync request with the same account/model produce equivalent
  results.

---

## ADR-AGENT-005: In-process coordinator with SQLite lease recovery (Phase 1)

Status: Proposed

### Context

Single API process today; no broker. Restart-safe execution needed.

### Decision

A background coordinator thread in the API process claims `queued` jobs via
compare-and-swap; `lease_owner` + `lease_expires_at` allow a restarted
process to reclaim stale `running` jobs.

### Alternatives Considered

- Separate worker process / Redis queue: rejected for Phase 1 (no scale
  need; `CLAUDE.md` §10).

### Consequences

- One process owns execution; a crash mid-job is recovered by the lease
  sweep (re-queue or fail).

### Validation Required

- Kill-restart test: a `running` job is not stuck after restart.

---

## ADR-AGENT-006: Idempotency via Idempotency-Key + request hash

Status: Proposed

### Context

Agents retry automatically; duplicate submissions must not create duplicate
jobs or duplicate provider spend.

### Decision

`Idempotency-Key` header (or body `idempotency_key`, header wins) +
`request_hash` (sha256 canonical JSON). Same key+hash → return original;
same key+different hash → 409.

### Alternatives Considered

- Client-request-id-only dedup: rejected — not a true idempotency token.

### Consequences

- Key retention until job expiry; partial unique index on
  `idempotency_key`.

### Validation Required

- Concurrent duplicate submissions yield one job.

---

## ADR-AGENT-007: Logical agent-vs-operator route separation (Phase 1)

Status: Proposed

### Context

Agent and operator endpoints share the same shared key today — an agent can
reach capture-management admin routes (`SECURITY_MODEL.md`).

### Decision

Introduce `CHATGPT_AGENT_API_KEY` (proposed) for `/v1/agent/*`; the operator
`CHATGPT_API_KEY` gates `/v1/chatgpt/admin/*`. Agent key cannot reach admin
routes. Falls back to single-key compat with a startup warning.

### Alternatives Considered

- Full per-client RBAC now: rejected — Phase 5 scope.

### Consequences

- Reduces (does not eliminate) blast radius; still single-tenant.

### Validation Required

- Agent key returns 403 on `/v1/chatgpt/admin/*`.

---

## ADR-AGENT-008: Reuse bridge-console for the Agent Job UI

Status: Proposed

### Context

`apps/bridge-console` is a Svelte 5 SPA with hash routing, `apiFetch`, and
reusable `Badge`/`MetricGrid`/`CodeBlock`/`ImageResult` components
(`CURRENT_SYSTEM_ASSESSMENT.md` §6).

### Decision

Add the Agent Job UI as new pages in `bridge-console`. No third frontend.

### Alternatives Considered

- Separate app: rejected — no repository evidence justifies it; duplicates
  build/auth/api-client.

### Consequences

- Console grows; keep pages modular.

### Validation Required

- `bun run check` + `build` pass; existing pages unchanged.

---

## ADR-AGENT-009: UI polling first, SSE later

Status: Proposed

### Context

Controlled polling is simpler, robust to disconnects, and matches the
existing console pattern (no auto-SSE today).

### Decision

Phase 1 UI uses controlled polling (5s dashboard, 3s detail, backoff on
terminal). SSE `/events` lands in Phase 3 with polling fallback.

### Alternatives Considered

- SSE from day one: rejected — adds a streaming contract before the state
  machine is stable.

### Validation Required

- Polling backoff and tab-hidden pause work.

---

## ADR-AGENT-010: Future object-storage adapter behind a Protocol

Status: Proposed

### Context

Single-host local files suffice now, but multi-host/cross-host access may
come.

### Decision

Define an `ArtifactStorage` Protocol (`put/get/delete/exists/metadata`);
`LocalArtifactStorage` now, `S3ArtifactStorage` only when triggered.

### Alternatives Considered

- Hardcode local FS forever: rejected — would force a rewrite later.

### Consequences

- A thin abstraction to maintain.

### Validation Required

- Local impl passes the same interface tests an S3 impl would.

---

## ADR-AGENT-011: Future queue-broker threshold

Status: Proposed

### Context

SQLite claim works for one process.

### Decision

Add Redis (leases + queue pointer, never authoritative binaries) **only**
when multiple worker nodes are needed or sustained >~50 jobs/min.

### Alternatives Considered

- Redis from day one: rejected — unnecessary dependency.

### Consequences

- None now; clear trigger documented.

### Validation Required

- n/a (deferred).

---

## ADR-AGENT-012: Future multi-client security threshold

Status: Proposed

### Context

Single shared key is the current reality; multi-tenant is out of scope
(`CLAUDE.md` §8).

### Decision

Per-client keys/scopes/quotas/tenant ownership + signed artifact URLs are
Phase 5, only when external multi-client use is required.

### Alternatives Considered

- Claim multi-tenant safety now: rejected — false; not implemented.

### Consequences

- Phase 1 deployments must stay private/trusted.

### Validation Required

- n/a (deferred); do not claim controls that don't exist.
