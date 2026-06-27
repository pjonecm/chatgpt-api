# API Contract — AI Agent → ChatGPT API Bridge

> **Status (2026-06-27): Phase 1C.3 non-streaming chat execution shipped** in
> `chatgpt_api/api/agent_job_routes.py`, dispatched from `openai_compat.py`.
> The routes below (`POST /v1/agent/jobs`, list, status, result, events,
> artifacts, cancel) are implemented for `chat` and `deep_research` only.
> Non-streaming `chat` jobs now execute through the same shared internal
> text-execution adapter used by synchronous `POST /v1/chat/completions`.
> Successful chat jobs persist both a durable `job_results` row and
> `outputs/agent-jobs/<job_id>/results/response.json`. `deep_research`
> submissions remain accepted but queued for a later phase, events remain
> JSON-only (no SSE), and running cancellation is still best-effort at the
> durable job-state level rather than a reliable provider hard-stop.
> Not the official OpenAI API — "OpenAI-shaped".

## Routes

```text
POST   /v1/agent/jobs                      submit a durable job
GET    /v1/agent/jobs                      list/filter/paginate jobs
GET    /v1/agent/jobs/{job_id}             job status
GET    /v1/agent/jobs/{job_id}/result      final result (text/json/image/research)
GET    /v1/agent/jobs/{job_id}/events      JSON event list (SSE deferred to Phase 3)
POST   /v1/agent/jobs/{job_id}/cancel      request cancellation
POST   /v1/agent/jobs/{job_id}/retry       operator-initiated retry (Phase 2)
GET    /v1/agent/jobs/{job_id}/artifacts   list artifacts for a job
GET    /v1/chatgpt/files/{file_id}/{filename}   (existing) artifact download
```

All routes require `Authorization: Bearer <CHATGPT_API_KEY>` (same shared key
in Phase 1; agent/operator separation is logical only — see
`SECURITY_MODEL.md`).

## 1. Job submission — `POST /v1/agent/jobs`

### Headers

- `Authorization: Bearer <key>` (required)
- `Idempotency-Key: <string>` (optional; recommended for agent retries)
- `Content-Type: application/json`

### Body — common fields

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `type` | string | yes | `chat` \| `deep_research` in the current shipped route service; image/multimodal job types are deferred |
| `model` | string | yes | alias from `GET /v1/models` (existing) |
| `client_request_id` | string | no | caller correlation id |
| `idempotency_key` | string | no | body equivalent of header; header wins |
| `priority` | int | no | deferred; not accepted by the current shipped route service |
| `callback_url` | string | no | deferred; not accepted by the current shipped route service |
| `max_attempts` | int | no | default from policy; overrides retry cap |
| `expires_at` | string | no | ISO8601; job auto-expires after |

### 1.1 Text / chat job

```json
{
  "type": "chat",
  "model": "auto",
  "messages": [{"role": "user", "content": "Explain this repository architecture."}],
  "stream": false,
  "client_request_id": "agent-run-123",
  "idempotency_key": "agent-run-123-step-4"
}
```

- `messages`: OpenAI-shaped; in the current shipped route service they are
  validated as string content only.
- `stream=false`: eligible for Phase 1C.3 coordinator execution.
- `stream=true`: accepted at submission time but **not supported by the
  current executor**; the job does not stream and will not produce a
  successful streaming result in Phase 1C.3.

### 1.2 Image-generation job

Deferred to Phase 2. Not accepted by the current shipped route service.

```json
{
  "type": "image_generation",
  "model": "gpt-image-1",
  "prompt": "A cinematic product advertisement for a blue glass app icon, no text.",
  "size": "1024x1024",
  "client_request_id": "campaign-77-frame-1",
  "idempotency_key": "campaign-77-frame-1-v1"
}
```

- `n` is fixed to 1 (existing bridge behavior, `CLAUDE.md` §12).
- `size`/`aspect_ratio`: existing supported set.

### 1.3 Multimodal / vision job

Deferred to Phase 2. Not accepted by the current shipped route service.

```json
{
  "type": "vision",
  "model": "auto",
  "mode": "ocr",
  "prompt": "Extract the visible letters only.",
  "images": ["data:image/png;base64,..."],
  "client_request_id": "ocr-9",
  "idempotency_key": "ocr-9-v1"
}
```

- Inputs accepted (reuse `image_inputs.py`): local path (server-side), public
  URL, `data:image/...;base64,...`, raw base64, or existing artifact
  reference `{"artifact_file_id": "file_..."}` (ownership-checked).
- MIME restricted to: `image/png`, `image/jpeg`, `image/webp`, `image/gif`.
- Max 10 images per request (existing limit). Max size per image: 20 MiB
  (proposed). Max total request: 25 MiB (proposed).
- Unsupported input → 400 `invalid_request_error`.

### 1.4 Image-edit job

Deferred to Phase 2. Not accepted by the current shipped route service.

```json
{
  "type": "image_edit",
  "model": "gpt-image-1",
  "prompt": "Change the icon letters to FW while preserving style.",
  "images": ["data:image/png;base64,..."],
  "aspect_ratio": "1:1",
  "client_request_id": "edit-3",
  "idempotency_key": "edit-3-v1"
}
```

- `mask`: **not supported** (existing bridge does not implement masks).
- One output image (existing).

### 1.5 Deep Research job

```json
{
  "type": "deep_research",
  "model": "chatgpt-deep-research",
  "messages": [{"role": "user", "content": "Research whether LLMs can reach AGI. Concise."}],
  "client_request_id": "research-42",
  "idempotency_key": "research-42-v1"
}
```

- Long-running (up to `CHATGPT_WEB_TIMEOUT=5400`s). UI must warn.
- Normal (non-temporary) chat mode enforced (existing).

## 2. Job acceptance response (201)

```json
{
  "job_id": "job_01HXYZ...",
  "status": "queued",
  "type": "chat",
  "created_at": "2026-06-27T12:00:00Z",
  "status_url": "/v1/agent/jobs/job_01HXYZ...",
  "result_url": "/v1/agent/jobs/job_01HXYZ.../result",
  "events_url": "/v1/agent/jobs/job_01HXYZ.../events",
  "artifacts_url": "/v1/agent/jobs/job_01HXYZ.../artifacts"
}
```

- Duplicate idempotency key + same payload → 200 with the original job
  (not 201).
- Same key + different payload → 409 `idempotency_conflict`.

## 3. Job status — `GET /v1/agent/jobs/{job_id}`

```json
{
  "job_id": "job_01HXYZ...",
  "type": "chat",
  "status": "running",
  "model": "auto",
  "account_alias": "main-free",
  "attempt_count": 1,
  "max_attempts": 3,
  "client_request_id": "agent-run-123",
  "created_at": "...",
  "queued_at": "...",
  "started_at": "...",
  "completed_at": null,
  "cancel_requested_at": null,
  "expires_at": null,
  "result_available": false,
  "artifact_count": 0,
  "error": null
}
```

- `status`: see state machine (`DATA_MODEL.md`).
- `error`: redacted `code` + `message` (no capture/cookie/token content).

## 4. Final result — `GET /v1/agent/jobs/{job_id}/result`

- 404 + `not_found` if the job id does not exist.
- 409 + `pending` if the job has not produced a result yet, including queued
  and running jobs.
- 409 + `job_failed` if the job reached `failed` without a stored result.
- 200 with a type-specific body:

### Text result

```json
{
  "job_id": "...",
  "result_type": "text",
  "model": "auto",
  "account_alias": "main-free",
  "finish_reason": "stop",
  "response": {"object": "chat.completion", "choices": [{"message": {"role": "assistant", "content": "..."}}]},
  "text": "..."
}
```

- `response` is loaded from the persisted
  `outputs/agent-jobs/<job_id>/results/response.json` payload.

### Image result

Future shape once image job execution ships.

```json
{
  "job_id": "...",
  "result_type": "image",
  "artifacts": [{"file_id": "file_...", "filename": "icon.png", "download_url": "http://<PUBLIC_BASE_URL>/v1/chatgpt/files/file_.../icon.png", "content_type": "image/png"}]
}
```

### Vision result

Future shape once vision job execution ships.

```json
{"job_id": "...", "result_type": "vision", "text": "FW", "response": {...}}
```

### Research result

Future shape once Deep Research Agent Job execution ships.

```json
{"job_id": "...", "result_type": "research", "artifacts": [{"file_id": "file_...", "filename": "llm-agi.md", "download_url": "...", "content_type": "text/markdown"}]}
```

### Error result

Illustrative terminal error shape.

```json
{"job_id": "...", "result_type": "error", "error": {"code": "chatgpt_auth_or_browser_challenge", "message": "capture expired or rejected"}}
```

## 5. Cancellation — `POST /v1/agent/jobs/{job_id}/cancel`

- Idempotent. Persists `cancel_requested_at`.
- For jobs that were still non-running when cancellation was requested
  (`accepted`, `validating`, `queued`, `retry_wait`), the in-process
  coordinator finalizes `cancel_requested → cancelled` without contacting the
  provider.
- Running cancellation is currently best-effort at the durable job-state
  level. The cancellation request is persisted, and a cancellation that wins
  the final state transition prevents success result persistence. The
  underlying provider request is not yet reliably interrupted in flight.
- 409 if already terminal (except `cancelled` → 200).
- Returns the updated status.

## 6. Events — `GET /v1/agent/jobs/{job_id}/events`

- **Phase 1:** not SSE; poll `GET /v1/agent/jobs/{job_id}` for status. The
  events endpoint returns a JSON array of `JobEvent`s (paginated) until SSE
  lands in Phase 3.
- **Phase 3:** `text/event-stream` of `data: {"event_type":"delta","text":"..."}`.
- Event types: `created`, `queued`, `attempt_started`, `delta`, `attempt_failed`,
  `artifact_saved`, `succeeded`, `failed`, `cancelled`.

## 7. Artifacts — `GET /v1/agent/jobs/{job_id}/artifacts`

```json
{"job_id": "...", "artifacts": [{"file_id": "file_...", "filename": "icon.png", "download_url": "...", "content_type": "image/png", "bytes": 12345}]}
```

Downloads reuse the existing `GET/HEAD /v1/chatgpt/files/{file_id}/{filename}`.

## 8. Listing — `GET /v1/agent/jobs`

Query params: `status`, `type`, `model`, `account`, `client_request_id`,
`error_code`, `created_after`, `created_before`, `limit` (default 50, max
200), `cursor` (created_at + job_id tuple for stable pagination), `sort`
(default `-created_at`).

```json
{"jobs": [ {...status object...} ], "next_cursor": "...", "has_more": true}
```

## 9. Idempotency

- `Idempotency-Key` header (preferred) or body `idempotency_key`; header wins
  on conflict.
- Scope: per-key global (single shared key in Phase 1). Key retained until
  job expiry/retention window.
- Request canonicalization → `request_hash` (sha256 of canonical JSON).
- Same key + same hash → return original job (200).
- Same key + different hash → 409 `idempotency_conflict`.
- Cancelled/expired job + same key → new job is allowed only if the prior is
  terminal; otherwise 409.

## 10. Error schema (OpenAI-shaped)

```json
{"error": {"type": "invalid_request_error", "code": "...", "message": "..."}}
```

Codes: `invalid_request_error`, `unauthorized`, `not_found`, `idempotency_conflict`,
`pending`, `cancel_conflict`, `retry_conflict`, `rate_limited`, plus existing
`chatgpt_model_limit`, `chatgpt_rate_limited`, `chatgpt_unsupported_model`,
`chatgpt_auth_or_browser_challenge` for provider errors.

## 11. Pagination / filtering

- Cursor-based (`created_at` + `job_id`) — stable under concurrent inserts.
- Filters combinable; no wildcard semantics on `client_request_id`.

## 12. UI-required fields (proposed backend requirements for the console)

- Dashboard summary: counts by status, oldest queued `created_at`, avg
  recent duration (needs `started_at`/`completed_at`).
- Table: `job_id`, `client_request_id`, `type`, `status`, `model`,
  `account_alias`, `attempt_count`, `created_at`, `started_at`, `duration`
  (derived), `result_type`, `error.code`.
- Detail: full status + request payload (redacted) + attempts + events +
  result + artifacts.
- Queue view: counts + coordinator state + stale-running jobs.
- Storage view: artifact counts + missing/orphan files (reconciliation).

These are **proposed API requirements** — fields not present on the existing
endpoints must be added when the agent-job tables are implemented.
