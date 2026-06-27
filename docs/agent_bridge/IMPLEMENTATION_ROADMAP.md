# Implementation Roadmap — AI Agent → ChatGPT API Bridge

> Phased plan. Backend + UI ordering prevents contract mismatch. No
> implementation in this task. Grounded in `CLAUDE.md` §14 (validation) and
> §15 (doc write-back).

## Phase 0 — Repository baseline (verify, don't change)

- **Objective:** confirm a green baseline.
- **In scope:** `python -m compileall chatgpt_api`; `python -m pytest -q`
  (expect 188 pass + 1 Windows `0o600` platform failure — documented, not a
  defect); `docker compose config --quiet`; frontend `bun run check`/`build`
  when bun available (NOT RUN otherwise).
- **Out of scope:** any code change.
- **Acceptance:** baseline recorded; Windows caveat documented.

## Phase 1 — Durable Agent Job Foundation (backend)

> **Status: Phase 1A (persistence) + Phase 1B (HTTP routes) implemented.**
> **Phase 1C.1 (retry schema + repository primitives) implemented.**
> Phase 1C.2+ (in-process coordinator, startup recovery wiring, provider
> execution) remains proposed.

- **Objective:** restart-safe async jobs for text/chat + research.
- **In scope:**
  - Schema in `_migrate()`: `agent_jobs`, `job_results`, `job_events` (state
    transitions), `job_attempts`; add nullable `job_id` to `artifacts`. **(1A done)**
  - Repository methods on `BridgeAdminStore` (compare-and-swap transitions,
    claim, list with cursor, summary). **(1A done)**
  - Durable retry scheduling primitives: `next_retry_at` migration,
    `retry_wait` persistence, due-retry promotion, retry events. **(1C.1 done)**
  - State machine + restart-recovery sweep (stale lease → re-queue/fail). **(1A done)**
  - Idempotency (`Idempotency-Key` header + body key + `request_hash`). **(1A done — header parsing is 1B)**
  - Endpoints: `POST /v1/agent/jobs`, `GET /v1/agent/jobs`, `GET …/{id}`,
    `GET …/{id}/result`, `POST …/{id}/cancel`, `GET …/{id}/events` (JSON,
    not SSE), `GET …/{id}/artifacts`. **(1B done — chat + deep_research only;
    jobs queue but do not execute)**
  - In-process coordinator (single process; SQLite claim). **(not started)**
  - Reuse `AccountRouter` + `BoundedSemaphore` + `ChatGPTProvider`. **(not started)**
  - Local storage `outputs/agent-jobs/<job_id>/` (request.json, response.json). **(1A: metadata + path only; file writing is later)**
- **Out of scope:** image/multimodal inputs (Phase 2), SSE streaming,
  callbacks, per-client auth.
- **Schema changes:** additive tables only (idempotent). **(1A + 1C.1 done)**
- **API changes:** additive `/v1/agent/*`. **(1B done — see `docs/OPENAI_COMPATIBILITY.md`)**
- **Tests:** `tests/test_agent_jobs.py` (state machine, idempotency,
  retry scheduling/promotion,
  restart recovery, redaction) — synthetic data only. **(1A done — 82 tests)**
- **Docs:** `docs/OPENAI_COMPATIBILITY.md` add agent routes; **(1B)**
  `docs/ARCHITECTURE.md` note job layer; **(1A done)** `README.md` snapshot refresh. **(1B — no public behavior change in 1A)**
- **Acceptance:** a chat job survives a process restart and is retrievable;
  duplicate idempotency returns the original; redaction verified. **(1A: persistence-level; full restart-recovery is exercised by the recover_stale_jobs primitive + tests. Live restart requires the coordinator, 1B.)**
- **Risks:** `openai_compat.py` blast radius — implement job layer in a new
  module `chatgpt_api/api/agent_jobs.py` wired into the handler, not inlined
  into the 5.6k-line file (clear ownership boundary, tests green —
  `CLAUDE.md` §10 permits this). **(1A: module created; not yet wired into the handler — that is 1B.)**
- **Dependencies:** none new.

## Phase 1 UI — Read-only monitoring

- **In scope:** `agent-jobs` page (summary + table + filters), `job-detail`
  page (status, timeline, result, artifacts, error), controlled polling,
  `JobStatusBadge`/`JobTypeBadge`/`JobTimeline`/`ArtifactPreview`.
- **Out of scope:** submission forms.
- **Tests:** `bun run check` + build.
- **Acceptance:** every Phase 1 screen maps to a shipped endpoint.

## Phase 2 — Image and multimodal jobs (backend + UI)

- **In scope:** `job_inputs` table; uploaded image persistence with `sha256`
  + MIME sniff + limits; reuse `image_inputs.py`; image_generation,
  image_edit, vision job types; artifact association; SSE delta events for
  streaming chat jobs.
- **UI:** submission forms (chat/image/vision/edit), cancellation,
  idempotency input, client-side validation.
- **Tests:** synthetic image fixtures; upload validation; MIME reject.
- **Acceptance:** image/vision/edit jobs produce downloadable artifacts.

## Phase 3 — Integration reliability

- **In scope:** SSE `/events` stream; callback delivery (disabled/allowlist
  by default) + retry history; better retry/failover policy; operational
  metrics; audit records.
- **UI:** queue status, retry visibility, storage status, cleanup/reconcile,
  integration examples, callback status.
- **Acceptance:** SSE reconnect falls back to polling; callbacks retried
  with backoff.

## Phase 4 — External storage + distributed workers (only when triggered)

- **Triggers:** see `STORAGE_DESIGN.md` thresholds.
- **In scope:** `ArtifactStorage` protocol + `S3ArtifactStorage`; Redis for
  leases/queue; separate worker container; multi-node; leases/heartbeats;
  dead-letter; distributed metrics.
- **Acceptance:** shared artifact access across nodes; no double-execution.

## Phase 5 — Multi-client security

- **In scope:** per-client keys (hashed), scopes, quotas, tenant ownership,
  separate operator access, audit, signed artifact URLs, UI client
  management.
- **Acceptance:** agent key cannot reach admin routes; per-client quotas
  enforced.

## Retry and failure policy

| Error class | Retryable | Max attempts | Backoff | Failover |
| --- | --- | --- | --- | --- |
| ChatGPT rate limit (`chatgpt_rate_limited`) | yes | 3 | exp 30s→5m | yes |
| Provider busy / network timeout / connection reset | yes | 3 | exp 10s→2m | yes |
| Account concurrency unavailable | yes | 3 | 5s linear | yes |
| Browser challenge (`chatgpt_auth_or_browser_challenge`) | yes (once) | 2 | 60s | yes |
| Expired/invalid capture | **no (terminal)** | — | — | failover once, then `failed` |
| Invalid input / unsupported model / unsupported capability | **no (terminal)** | — | — | no |
| Storage / DB failure | **no (terminal)** | — | — | no |
| Worker crash | recovered by sweep | — | — | re-queue |
| Cancellation | n/a | — | — | n/a |
| Callback failure | yes (Phase 3) | 5 | exp | n/a |
| Artifact write failure | **no (terminal)** `storage_failure` | — | — | no |

- Expired captures are **not** endlessly retryable — terminal after one
  failover attempt.
- Errors normalized via existing `code`s; persisted redacted on
  `agent_jobs.error_*` + `job_attempts.error_*`.

## Ordered task sequence

1. Baseline verification.
2. Current-system assessment (done — `CURRENT_SYSTEM_ASSESSMENT.md`).
3. Workflows + wireframes (done — `UI_WORKFLOW.md`/`UI_WIREFRAMES.md`).
4. API contract (done — `API_CONTRACT.md`).
5. State machine + data model (done — `DATA_MODEL.md`).
6. Storage design (done — `STORAGE_DESIGN.md`).
7. Security boundaries (done — `SECURITY_MODEL.md`).
8. Durable job persistence + repository tests.
9. Job endpoints.
10. Execution coordinator + restart recovery.
11. Read-only monitoring UI.
12. Text-job submission UI.
13. Image/multimodal execution.
14. Image-related UI.
15. Queue/storage operations UI.
16. SSE/callback reliability.
17. Distributed infra only when thresholds reached.

## Validation commands (per phase)

- Backend: `python -m compileall chatgpt_api`; `python -m pytest -q`
  (expect the 1 Windows platform failure; never "fix" it by relaxing
  `0o600`).
- Agent jobs: `python -m pytest tests/test_agent_jobs.py -q`.
- Console: `bun run --cwd apps/bridge-console check && build` (NOT RUN if
  bun unavailable).
- Docker: `docker compose config --quiet`; smoke `curl /health` + `/v1/agent/jobs`.

## Documentation write-back

- `docs/OPENAI_COMPATIBILITY.md` — new `/v1/agent/*` routes.
- `docs/ARCHITECTURE.md` — agent-job layer + `agent_jobs.py` module.
- `docs/CLI.md` — if CLI job commands are added.
- `docs/DOCKER.md` / `.env.example` — new env (`CHATGPT_AGENT_API_KEY`,
  retention, limits).
- `README.md` — capability snapshot + validation date when public behavior
  changes.
- `docs/PROJECT_ANALYSIS.md` — surface ownership update.

## Explicitly deferred

- Redis, PostgreSQL, MinIO/S3, separate workers, Kubernetes.
- Per-client auth, RBAC, tenant isolation, signed URLs, audit.
- SSE streaming (Phase 3), callbacks (Phase 3).
- `n>1` images, masks, native tool-call API, real token usage (existing
  documented gaps — not "fixed").
