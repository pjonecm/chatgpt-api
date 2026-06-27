# UI Workflow — Agent Job Bridge Console

> Operator + integration-testing surface, **not** a consumer product. The UI
> is **not** the security boundary — all authorization is backend-enforced.
> Extends `apps/bridge-console` (Svelte 5, hash-routed, `apiFetch`,
  Tailwind v4, `lucide-svelte`). No third frontend.

## 1. UI purpose

Let operators monitor agent-submitted jobs, manually submit test jobs,
inspect request/result payloads, view artifacts, diagnose queue/storage,
and help developers integrate external agents — without ever exposing
captures, cookies, tokens, or keys.

## 2. User personas

- **Operator** — monitors health, cancels stuck jobs, diagnoses failures.
- **Integration tester** — submits test jobs before wiring a real agent.
- **Agent developer** — reads the integration page for endpoints/examples.

## 3. Primary workflows

1. Monitor live jobs → drill into a failing job → read redacted error →
   cancel or retry.
2. Submit a test chat/image/vision/edit/research job → follow it to detail.
3. Diagnose queue backlog / stale-running jobs / storage orphans.
4. Copy integration examples (base URL, endpoints, curl, idempotency).

## 4. Information architecture

Extend the existing `pages` constant (`App.svelte ~658-667`) with:

- `overview` (existing, extend with job summary card)
- `agent-jobs` (**new**) — dashboard + table + filters
- `submit-test` (**new**) — test submission forms (replaces some `test-lab`
  overlap; keep `test-lab` for synchronous testing)
- `job-detail` (**new**, hash `#jobs/<job_id>`)
- `queue` (**new**) — execution + storage status
- `accounts` (existing, reuse)
- `artifacts` (existing `storage`, extend with job-owned artifacts)
- `integration` (**new**) — agent integration help (superset of `api-docs`)
- `settings` (existing)

Navigation: top bar with the existing nav pattern; responsive collapse for
tablet. Desktop-first dense layout.

## 5. Navigation / route names

Hash routes: `#agent-jobs`, `#submit-test`, `#jobs/<job_id>`, `#queue`,
`#integration`. Existing `#accounts`, `#storage`, `#settings` unchanged.

## 6. Screen definitions

(See `UI_WIREFRAMES.md` for layouts.)

### 6.1 Agent Jobs Dashboard

- **Summary cards:** queued / running / retry-wait / succeeded / failed /
  cancelled counts, oldest queued age, avg recent duration. (Requires the
  proposed list endpoint + `created_at`/`started_at`/`completed_at`.)
- **Table:** job_id, client_request_id, type, status, model, account,
  attempt_count, created_at, started_at, duration, result_type, actions
  (view / cancel).
- **Filters:** search (client_request_id/job_id), status, type, model,
  account, date range, error_code.
- **States:** loading, empty, error, no-results, partial, API-unavailable.
- **Behavior:** default sort `-created_at`; cursor pagination; refresh
  interval 5s (controlled, pauses when tab hidden); manual refresh; row →
  `#jobs/<job_id>`; status badges; duration formatting; stale-job
  highlight; responsive table (horizontal scroll on narrow).

### 6.2 Submit Test Job

Forms: chat (model, system, user, prior messages, stream flag,
client_request_id, idempotency_key, sync/async toggle), image_generation
(prompt, model, size, ids), vision (prompt, image upload, MIME/size
validation, model, ids), image_edit (source image, prompt, aspect_ratio,
ids), deep_research (messages, ids; long-running warning). For each:
validation, accepted→navigate to detail, duplicate-idempotency 409 handling,
reset behavior. Clearly distinguish **synchronous** (existing test-lab) from
**asynchronous** (agent job) submission.

### 6.3 Job Detail

Sections: identity, status badge, type, model, client_request_id,
idempotency_key (partially redacted), timing, account routing, attempt_count,
request payload (redacted), input files, state-transition timeline, attempts,
provider info, progress/events, text result, raw normalized response,
generated/edited images, vision result, research report, artifact list,
error details, cancellation, manual retry (Phase 2). **Never display:**
capture contents, cookies, Authorization headers, sentinel/proof tokens,
keys, passphrases.

Result rendering: markdown (research), plain text, JSON viewer, image
preview + download, multiple artifacts, failed/missing-artifact state.

### 6.4 Queue and Execution Status

Counts (queued/running/retry-wait), oldest queued, coordinator state
(in-process), active job, per-account concurrency, per-capability capacity,
jobs waiting for capacity, stale-running jobs, recent failures, last
success, restart-recovery events. **Wording must match implementation**
("in-process coordinator", not "distributed cluster").

### 6.5 Storage and Artifact Status

Artifact count, known usage, artifact types, input/result usage, expired,
missing files, orphan files, failed cleanups, retention settings, last
cleanup run, reconciliation status. No MinIO/S3/Redis/Postgres controls
unless those are selected.

### 6.6 Agent Integration Page

Base URL, auth header format (`Authorization: Bearer <API_KEY>` —
placeholder, never the real key), endpoints, example payloads, curl,
Python client, idempotency behavior, error codes, file-size limits,
supported/unsupported capabilities, sync-vs-async guidance.

### 6.7 Account and Capacity Context

Reuse existing `accounts` view. Safe fields: alias, plan tier, capabilities,
availability, active concurrency, throttled state, capture health, last
check, recent failure category. No credentials.

## 7. Component inventory

| Component | Purpose | Inputs | API dep | Reuse | Phase |
| --- | --- | --- | --- | --- | --- |
| `JobStatusBadge` | status pill (label+icon, not color-only) | status | — | `Badge.svelte` | 1 |
| `JobTypeBadge` | request type | type | — | `Badge.svelte` | 1 |
| `JobTable` | list rows | jobs[] | list endpoint | table pattern | 1 |
| `JobFilters` | filter bar | filters | — | `Input` | 1 |
| `JobSummaryCards` | counts | summary | list summary | `MetricGrid.svelte` | 1 |
| `JobTimeline` | state transitions | events[] | events | — | 1 |
| `JobAttemptList` | attempts | attempts[] | status | — | 1 |
| `JobErrorPanel` | redacted error | error | — | `CaptureResult` | 1 |
| `ArtifactPreview` | image/markdown preview | artifact | download | `ImageResult.svelte` | 1 |
| `ArtifactList` | list | artifacts[] | artifacts endpoint | — | 1 |
| `RequestPayloadViewer` | redacted JSON | request | status | `CodeBlock.svelte` | 1 |
| `ResultViewer` | text/json/image/markdown | result | result endpoint | `CodeBlock`/`ImageResult` | 1 |
| `AccountCapacityCard` | safe capacity | account | existing usage | — | 1 |
| `QueueHealthPanel` | queue state | queue summary | queue endpoint | `MetricGrid` | 3 |
| `StorageSummary` | storage state | storage summary | storage endpoint | `MetricGrid` | 3 |
| `PollingStatus` | refresh indicator | — | — | — | 1 |
| `CopyableCodeBlock` | copy examples | code | — | `CodeBlock.svelte` | 1 |
| `SubmitChatJobForm` | chat form | — | submit endpoint | `Input`/`Textarea` | 2 |
| `SubmitImageJobForm` | image gen form | — | submit endpoint | `Input` | 2 |
| `SubmitVisionJobForm` | vision upload form | — | submit endpoint | `Input` | 2 |
| `SubmitImageEditJobForm` | edit form | — | submit endpoint | `Input` | 2 |

## 8. API-to-screen mapping

| Screen | Element | Endpoint (proposed) | Refresh | Missing backend |
| --- | --- | --- | --- | --- |
| Dashboard | summary cards | `GET /v1/agent/jobs?summary=1` (proposed) | 5s poll | summary aggregator |
| Dashboard | table | `GET /v1/agent/jobs` | 5s poll | list endpoint |
| Detail | status | `GET /v1/agent/jobs/{id}` | 3s poll | status endpoint |
| Detail | timeline | `GET /v1/agent/jobs/{id}/events` | 3s poll | events endpoint |
| Detail | result | `GET /v1/agent/jobs/{id}/result` | on terminal | result endpoint |
| Detail | artifacts | `GET /v1/agent/jobs/{id}/artifacts` | on terminal | artifacts endpoint |
| Submit | form | `POST /v1/agent/jobs` | one-shot | submit endpoint |
| Queue | panel | `GET /v1/agent/jobs/queue` (proposed) | 5s poll | queue summary |
| Storage | panel | `GET /v1/agent/jobs/storage` (proposed) | manual | storage summary |
| Integration | examples | static | none | — |

## 9. Status presentation (not color-only)

| Status | Label | Badge | Icon | Auto-refresh | Terminal | Actions |
| --- | --- | --- | --- | --- | --- | --- |
| accepted | Accepted | neutral | clock | yes | no | view |
| validating | Validating | neutral | spinner | yes | no | view |
| queued | Queued | blue | hourglass | yes | no | view, cancel |
| running | Running | amber | play | yes | no | view, cancel |
| streaming | Streaming | amber | activity | yes | no | view, cancel |
| retry_wait | Retry wait | amber | refresh-cw | yes | no | view, cancel |
| cancel_requested | Cancel requested | purple | x-circle | yes | no | view |
| succeeded | Succeeded | green | check | no | yes | view, retry |
| failed | Failed | red | alert-octagon | no | yes | view, retry |
| cancelled | Cancelled | gray | ban | no | yes | view |
| expired | Expired | gray | clock-expired | no | yes | view |

Each badge has a label + icon + supporting text (never color alone).

## 10. Error / state presentation

- Loading: skeleton rows.
- Empty: "No jobs yet" + CTA to submit-test.
- Error: redacted message + retry button.
- Authorization failure: "Unauthorized — check API key in Settings."
- Server unavailable: "Bridge unreachable" + last-known data.
- Storage unavailable: storage panel shows "unavailable".
- Job disappeared: 404 → "Job not found (expired or unknown)."
- Artifact missing: row shows "file missing" with reconcile action.
- Cancel conflict: 409 toast.
- Retry conflict: 409 toast.
- Duplicate idempotency: 409 → link to existing job.
- Polling backoff: exponential 3s→10s cap when terminal.
- SSE disconnect (Phase 3): fall back to polling.

## 11. Artifact behavior

- Image: inline preview + download link (existing `ImageResult` pattern).
- Research: markdown render + download `.md`.
- Multiple: stacked list.
- Missing: "file missing" state.

## 12. Responsive + accessibility

- Desktop-first; tablet usable (table horizontal scroll, nav collapse).
- Accessible labels (`aria-label`), keyboard navigation, visible focus,
  status not color-only, sufficient contrast.

## 13. Security and redaction

- The configured API key is never rendered (placeholder `<API_KEY>`).
- Request payload viewer redacts `authorization`/`cookie`/sentinel headers
  via the backend redaction (reuse `_redacted_headers`); the UI also
  defensively masks any key named `*token*`/`*key*`/`*secret*`.
- No capture content, ever.

## 14. Phase 1 vs future UI scope

- Phase 1 UI: read-only monitoring (dashboard, table, detail, timeline,
  result, artifacts, error).
- Phase 2 UI: submission forms + cancellation.
- Phase 3 UI: queue/storage/integration.
- Phase 4 UI: client management (only after Phase 5 backend).

## 15. Acceptance criteria

See task §23 — every Phase 1 screen maps to a proposed API contract; every
state has a visual; sensitive fields excluded; existing console reused; no
UI assumes unsupported backend behavior; empty/loading/error states defined;
accessibility + responsive defined; polling/SSE explicit.
