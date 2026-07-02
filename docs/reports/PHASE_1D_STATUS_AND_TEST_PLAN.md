# Phase 1D Current Status and Test Plan

## 1. Executive Verdict

**Verdict: `PHASE 1D NOT ACCEPTED — DEFECTS FOUND`**

Live API and browser validation was executed on 2026-06-30 and is recorded in
`docs/reports/PHASE_1D_LIVE_BROWSER_VALIDATION.md`.

Phase 1D is not accepted because the existing succeeded Deep Research Agent Job
has a durable research result but no associated artifact row. The live API
returns `500 storage_failure` for:

```text
GET /v1/agent/jobs/job_aeb0a8d9ae66bf34adf354f5/result
```

and:

```text
GET /v1/agent/jobs/job_aeb0a8d9ae66bf34adf354f5/artifacts
```

returns HTTP 200 with an empty `artifacts` array. Therefore the required
markdown artifact, preview/download, and artifact `HEAD` acceptance criteria
failed.

Live validation did pass API startup, health, list/filter/status/events, chat
result, failed/cancelled/unknown/unauthorized behavior, dashboard rendering of
all five existing jobs, chat/failed/cancelled detail routes, API outage and
recovery behavior, restart persistence of the five job records, responsive
table basics, and no-secret rendering checks. The research artifact failure is
blocking.

Phase 1D's read-only Agent Job Monitoring UI is substantially implemented and maps to the shipped Phase 1 backend endpoints by static inspection. The dashboard and detail pages use real `/v1/agent/jobs*` endpoints, do not use mocked job data, keep summaries page-local, use controlled polling, and avoid Phase 2-only submission/retry/queue controls.

Previous readiness findings before live validation:

- **RESOLVED:** the bridge-console no longer renders the configured API key in clear text. Visible shell/Overview fields now use `********`, API-key inputs use password fields, and generated curl/CLI/opencode snippets use `<API_KEY>` placeholders.
- **RESOLVED:** frontend validation ran successfully through the safe npm fallback (`npm.cmd`) because `node_modules` already existed and no install or lockfile rewrite was required.
- **LIVE VALIDATION NOT RUN:** the API was not reachable at `http://127.0.0.1:8000/health`, and no browser validation was run.

Static inspection, backend tests, frontend `svelte-check`, and frontend build are now passing except for the known Windows NTFS full-suite caveat. Acceptance still requires live browser validation against the real running API and migrated Agent Job records.

## 2. Repository and Environment Status

Repository status after the API-key exposure fix:

- `git status --short`: modified `apps/bridge-console/src/App.svelte`, modified `apps/bridge-console/src/lib/Input.svelte`, untracked `docs/reports/PHASE_1D_STATUS_AND_TEST_PLAN.md`, and unrelated untracked `.claude/settings.local.json`; warning reading the user global git ignore due permission denied.
- `git log --oneline -15`: tip is `7ba20ed Add read-only agent job monitor`, followed by Phase 1C.5 and Phase 1C commits.
- `git diff --check`: PASS, with line-ending warnings that Git will replace LF with CRLF for the edited Svelte files.
- Frontend runtime: `bun` unavailable; `node v24.14.0`, `npm.cmd 11.9.0`, and `npx.cmd` available; `apps/bridge-console/node_modules` already present; only `bun.lock` exists.

Environment inventory, redacted:

```text
account_capture_present=true
account_capture_count=2
account_aliases=free,main-free
capture_content_displayed=false
chatgpt_api_key_env_present=false
chatgpt_api_key_value_displayed=false
admin_db_present=true
agent_jobs_table_present=true
existing_agent_jobs=5
agent_jobs_queued=0
agent_jobs_running=0
agent_jobs_succeeded=2
agent_jobs_failed=1
agent_jobs_cancelled=2
job_artifact_count=1
research_artifact_present=true
api_health=not_reachable
```

Existing safe job inventory:

```text
succeeded chat job present=true
succeeded deep_research job present=true
failed job present=true
cancelled chat job present=true
cancelled deep_research job present=true
research markdown artifact present=true
active queued/running job present=false
```

## 3. Phase 1D Feature Matrix

| Capability | Status | Evidence | Notes |
| --- | --- | --- | --- |
| Agent Jobs navigation entry | IMPLEMENTED | `apps/bridge-console/src/App.svelte:660-669` | New `agent-jobs` page is in the existing page list. |
| Dashboard hash route | IMPLEMENTED | `App.svelte:897-919` | `#agent-jobs` maps to page state. |
| Job detail hash route | IMPLEMENTED | `App.svelte:903-919` | `#jobs/<job_id>` maps to `job-detail`. |
| Direct navigation to detail URL | IMPLEMENTED BUT UNVERIFIED | `App.svelte:863-919` | `applyHashRoute(location.hash...)` runs on mount; needs browser refresh validation. |
| Browser refresh on detail route | IMPLEMENTED BUT UNVERIFIED | `App.svelte:863-919` | Static support exists; browser not run. |
| Existing console routes unchanged | IMPLEMENTED BUT UNVERIFIED | `App.svelte:660-669`, `App.svelte:3356-3370` | Static route list preserved; no browser regression run. |
| Real job list endpoint | IMPLEMENTED | `AgentJobsPage.svelte:75-77`, `api.ts:68-85` | Calls `/agent/jobs`; no mock data found. |
| Table columns use backend fields | IMPLEMENTED | `JobTable.svelte:20-64`, `agent_job_routes.py:274-297` | Fields map to serialized status shape. |
| Page-local summaries | IMPLEMENTED | `AgentJobsPage.svelte:124-155` | UI explicitly says counts apply only to loaded page (`:135-139`). |
| Global summary metrics avoided | IMPLEMENTED | `AgentJobsPage.svelte:135-139`, `:182-189` | No global total claim. |
| Sorting behavior | IMPLEMENTED | `agent_jobs.py:600-640` | Backend sorts newest-first; UI does not invent client sort. |
| Pagination | IMPLEMENTED | `AgentJobsPage.svelte:30-33`, `:111-121`, `:182-194`; `agent_jobs.py:600-645` | Cursor stack uses `next_cursor`. |
| Supported filters | IMPLEMENTED | `JobFilters.svelte:16-30`, `api.ts:74-82`, `agent_job_routes.py:616-653` | Status/type/model/account/client_request_id/error_code map to backend. Job ID search is page-local and labeled as such. |
| Unsupported future filters avoided | IMPLEMENTED | `JobFilters.svelte:88-90` | No date-range, queue-health, worker, or storage-health filters in Phase 1D UI. |
| Job status detail | IMPLEMENTED | `AgentJobDetailPage.svelte:89-93`, `api.ts:91-97` | Calls `GET /agent/jobs/{job_id}`. |
| Events timeline | IMPLEMENTED | `AgentJobDetailPage.svelte:102-108`, `JobTimeline.svelte` | Calls shipped JSON events endpoint. |
| Result loading only when appropriate | PARTIALLY IMPLEMENTED | `AgentJobDetailPage.svelte:120-137` | It calls result each refresh, but treats 409 `pending` and `job_failed` safely. |
| Artifacts loading | IMPLEMENTED | `AgentJobDetailPage.svelte:111-117`, `api.ts:107-113` | Calls shipped artifacts endpoint. |
| Pending/succeeded/failed/cancelled rendering | IMPLEMENTED BUT UNVERIFIED | `JobResultViewer.svelte:70-85` | Static handling exists; browser not run. |
| Deep Research markdown preview/link | IMPLEMENTED BUT UNVERIFIED | `AgentJobDetailPage.svelte:140-153`, `JobResultViewer.svelte:40-65` | Fetches markdown through artifact URL and renders as preformatted text. |
| Chat text result display | IMPLEMENTED BUT UNVERIFIED | `JobResultViewer.svelte:33-39` | Needs browser validation with existing succeeded chat job. |
| Jobs without results/artifacts | IMPLEMENTED | `JobResultViewer.svelte:78-85`, `JobArtifactList.svelte:21-23` | Does not show false success panels. |
| Unknown job/not-found state | IMPLEMENTED BUT UNVERIFIED | `AgentJobDetailPage.svelte:171-179`; backend `_not_found` via `agent_job_routes.py:465-479` | Static handling exists; browser/API smoke not run. |
| Loading state | IMPLEMENTED | `AgentJobsPage.svelte:172-175`, `AgentJobDetailPage.svelte:171-175` | Present. |
| Empty and no-results states | IMPLEMENTED | `AgentJobsPage.svelte:172-179` | Empty DB and page-local no-results states present. |
| Unauthorized state | IMPLEMENTED BUT UNVERIFIED | `AgentJobsPage.svelte:162-165`, `AgentJobDetailPage.svelte:175-178` | Needs browser/API test with invalid key. |
| API-unavailable state | PARTIALLY IMPLEMENTED | `api.ts:24-33`, `AgentJobsPage.svelte:162-168` | Network failure surfaces as refresh failure and preserves last-known rows; copy says refresh failed, not specifically "Bridge unreachable". |
| Controlled polling | IMPLEMENTED | Dashboard `AgentJobsPage.svelte:57-59`; detail `AgentJobDetailPage.svelte:69-71` | Dashboard 5s, detail 3s. |
| Hidden-tab polling pause | IMPLEMENTED BUT UNVERIFIED | Dashboard `:50-59`; detail `:61-71` | Uses `document.hidden`; browser not run. |
| Polling cleanup | IMPLEMENTED BUT UNVERIFIED | Dashboard `:60-68`; detail `:72-80` | Clears intervals on unmount/destroy; repeated navigation needs browser validation. |
| Overlap prevention | IMPLEMENTED | Dashboard `:70-87`; detail `:82-99` | `refreshInFlight` gate. |
| Transient failure preserves data | IMPLEMENTED | `AgentJobsPage.svelte:82-87`, `:162-168`; detail keeps existing `job` on status failure | Dashboard explicitly shows last-known page data. |
| Responsive table | IMPLEMENTED BUT UNVERIFIED | `JobTable.svelte:16-17` | Horizontal overflow exists; visual check pending. |
| Basic accessibility | PARTIALLY IMPLEMENTED | `JobTable.svelte:64`, `AgentJobsPage.svelte:172-173` | Some labels/aria-live exist; keyboard/focus validation not run. |

## 4. Backend-to-UI Contract Mapping

| UI field or behavior | Backend endpoint | Actual backend field | Supported | Notes |
| --- | --- | --- | --- | --- |
| Job ID | `GET /v1/agent/jobs`, `GET /v1/agent/jobs/{id}` | `job_id` | Yes | Serialized in `serialize_status` (`agent_job_routes.py:279`). |
| Client request ID | Same | `client_request_id` | Yes | `agent_job_routes.py:286`. |
| Job type | Same | `type` from `request_type` | Yes | `agent_job_routes.py:280`. |
| Status | Same | `status` | Yes | `agent_job_routes.py:281`. |
| Model | Same | `model` | Yes | `agent_job_routes.py:282`. |
| Account alias | Same | `account_alias` | Yes | `agent_job_routes.py:283`. |
| Attempt count | Same | `attempt_count`, `max_attempts` | Yes, summary only | Individual attempt rows exist in repository but are not exposed by route; UI says so (`AgentJobDetailPage.svelte:225-228`). |
| Created timestamp | Same | `created_at` | Yes | `agent_job_routes.py:287`. |
| Queued timestamp | Same | `queued_at` | Yes | `agent_job_routes.py:288`. |
| Started timestamp | Same | `started_at` | Yes | `agent_job_routes.py:289`. |
| Completed timestamp | Same | `completed_at`, `cancelled_at` | Yes | `agent_job_routes.py:290-292`. |
| Error code/message | Same | `error.code`, `error.message` | Yes | `agent_job_routes.py:274-297`; repository sanitizes error messages. |
| Result availability | Same | `result_available` | Yes | Derived from `job.result_id is not None` (`agent_job_routes.py:294`). |
| Result type | `GET /v1/agent/jobs/{id}/result` | `result_type` | Yes when result exists | `agent_job_routes.py:300-323`. |
| Text result | Result endpoint | `text` | Yes | Rendered by `JobResultViewer.svelte:33-39`. |
| Research artifact | Result/artifacts endpoint | `artifacts[]` | Yes | Research result fails closed if artifact missing (`agent_job_routes.py:498-507`). |
| Events | `GET /v1/agent/jobs/{id}/events` | `events[]` | Yes, JSON only | `agent_job_routes.py:511-522`; no SSE. |
| Attempts | None in HTTP contract | Not exposed as list | Partially | UI shows count only and states row contract is absent. |
| Artifacts | `GET /v1/agent/jobs/{id}/artifacts` | `artifacts[]` | Yes | Path is excluded; download URL is relative. |
| Pagination cursor | `GET /v1/agent/jobs` | `next_cursor`, `has_more` | Yes | Cursor is `created_at|job_id` (`agent_jobs.py:600-604`). |
| Filters | `GET /v1/agent/jobs` | `status`, `type`, `model`, `account`, `client_request_id`, `error_code`, `limit`, `cursor` query params | Yes | `created_after`, `created_before`, `sort`, queue health, and global search are not shipped. |
| Summary counts | List endpoint | None global | Safely derived | UI derives from loaded page and labels page-local. |
| Duration | Status fields | Derived from timestamps | Safely derived | `formatting.ts:51-69`. |
| Progress indicators | Events/status | Timeline event list; polling status | Partially | No percent/progress metric exists; UI does not claim one. |
| Queue health | None | None | No | Not rendered in Phase 1D. |
| Worker heartbeat/distributed metrics | None | None | No | Not rendered in Phase 1D. |

## 5. Automated Validation Results

| Command | Working directory | Result | Important output |
| --- | --- | --- | --- |
| `git status --short` | `C:\Development\chatgpt-api` | PASS | Only `?? .claude/settings.local.json`; git emitted user-global ignore permission warnings. |
| `python -m compileall chatgpt_api` | `C:\Development\chatgpt-api` | PASS | Byte-compile listing completed. |
| `python -m pytest tests/test_agent_jobs.py -q` | `C:\Development\chatgpt-api` | PASS | `96 passed in 3.80s`. |
| `python -m pytest tests/test_openai_compat.py -q` | `C:\Development\chatgpt-api` | PASS | `88 passed in 1.11s`. |
| `python -m pytest -q` | `C:\Development\chatgpt-api` | FAIL, known Windows platform caveat | `379 passed`, one failure: `tests/test_crypto.py::test_load_secrets_key_creates_owner_only_key_file`, expected POSIX `0o600` but NTFS reported `0o666` (`438 == 384`). |
| `bun --version` | `C:\Development\chatgpt-api` | FAIL, environmental | `bun` is not recognized. |
| `node --version` | `C:\Development\chatgpt-api` | PASS | `v24.14.0`. |
| `npm.cmd --version` | `C:\Development\chatgpt-api` | PASS | `11.9.0`; used because PowerShell blocks `npm.ps1`. |
| `npm.cmd --prefix apps/bridge-console run check` | `C:\Development\chatgpt-api` | PASS | `svelte-check found 0 errors and 0 warnings`. |
| `npm.cmd --prefix apps/bridge-console run build` | `C:\Development\chatgpt-api` | PASS | Vite built successfully; 134 modules transformed. |
| Static secret scan | `C:\Development\chatgpt-api` | PASS by manual classification | Remaining `apiKey` matches are internal headers/state/localStorage/password inputs/props; visible snippets use placeholders. |
| `docker compose config --quiet` | `C:\Development\chatgpt-api` | PASS with warnings | Compose config parsed; Docker warned it could not read `C:\Users\Javit-PC-LLM\.docker\config.json` due access denied. |

No live API smoke tests were run because the API was not reachable at `127.0.0.1:8000`.

## 6. Existing Test Coverage

Backend coverage exists for:

- Agent Job schema, repository state machine, idempotency, retry primitives, restart recovery, redaction: `tests/test_agent_jobs.py`.
- Agent Job HTTP route service and HTTP integration, including list, filters, pagination, status, result pending, seeded result, missing payload, events JSON, artifacts, cancel, auth: `tests/test_agent_job_routes.py`.
- Coordinator lifecycle, retry promotion, cancellation finalization, job execution behavior: `tests/test_agent_job_coordinator.py`.
- Text and Deep Research execution adapters: `tests/test_agent_job_text_execution.py`, `tests/test_agent_job_research_execution.py`.
- Facade integration and existing route behavior: `tests/test_openai_compat.py`.

Frontend coverage gaps:

- No established frontend unit/e2e tests were found for `apps/bridge-console`.
- No automated coverage for hash route parsing, job list rendering, job detail rendering, status/result/artifact/error rendering, polling cleanup, filter serialization from UI, unauthorized/API-unavailable states, empty/no-results states, Deep Research artifact preview, cancelled job display, or existing console page regression.
- Because no frontend test harness exists, Phase 1D browser validation must cover these gaps before acceptance.

## 7. Live-Test Prerequisites

Available now:

- Account captures present: `true` (2 aliases detected; contents not displayed).
- Admin SQLite DB present: `true`.
- Existing Agent Job records: `5`.
- Successful chat job: `true`.
- Successful Deep Research job: `true`.
- Research markdown artifact: `true`.
- Cancelled jobs: `true` (chat and Deep Research terminal cancelled records exist).
- Failed job: `true`.
- Docker compose config validation: available.

Blocked or unavailable now:

- Running API: `false` (`/health` not reachable).
- Running bridge-console dev server: blocked because `bun` is unavailable.
- Frontend check/build: blocked because `bun` is unavailable.
- Active pending/running job for pending-result polling: not present in current DB.
- Distinguishing cancelled queued vs cancelled running from static DB: not confidently established; the two cancelled jobs include attempt-started events, so they appear to cover running cancellation, not queued-only cancellation.

## 8. Tests Available Now

### 8.1 Automated Tests

Run from `C:\Development\chatgpt-api`:

```powershell
git status --short
python -m compileall chatgpt_api
python -m pytest tests/test_agent_jobs.py -q
python -m pytest tests/test_openai_compat.py -q
python -m pytest -q
docker compose config --quiet
```

Expected:

- Compileall passes.
- `tests/test_agent_jobs.py` passes.
- `tests/test_openai_compat.py` passes.
- Full pytest passes except the known Windows NTFS `0o600` caveat in `tests/test_crypto.py`.
- Docker compose config exits 0; local Docker config permission warnings may appear.

Preferred Bun commands remain:

```powershell
bun run --cwd apps/bridge-console check
bun run --cwd apps/bridge-console build
```

The current environment used this safe fallback because Bun is unavailable, `node_modules` already exists, and no install was needed:

```powershell
npm.cmd --prefix apps/bridge-console run check
npm.cmd --prefix apps/bridge-console run build
```

Expected:

- Both must pass before Phase 1D browser acceptance.

### 8.2 Backend API Smoke Tests

Use the actual route shapes in code. Start the API separately, then:

```powershell
$BaseUrl = "http://127.0.0.1:8000"
$ApiKey = "<API_KEY>"
$Headers = @{ Authorization = "Bearer $ApiKey" }

Invoke-RestMethod "$BaseUrl/health"
Invoke-RestMethod "$BaseUrl/v1/agent/jobs?limit=5" -Headers $Headers
Invoke-RestMethod "$BaseUrl/v1/agent/jobs?status=succeeded&limit=5" -Headers $Headers
Invoke-RestMethod "$BaseUrl/v1/agent/jobs?type=chat&limit=5" -Headers $Headers

$Jobs = Invoke-RestMethod "$BaseUrl/v1/agent/jobs?limit=5" -Headers $Headers
$KnownJobId = $Jobs.jobs[0].job_id

Invoke-RestMethod "$BaseUrl/v1/agent/jobs/$KnownJobId" -Headers $Headers
Invoke-RestMethod "$BaseUrl/v1/agent/jobs/$KnownJobId/events" -Headers $Headers
Invoke-RestMethod "$BaseUrl/v1/agent/jobs/$KnownJobId/result" -Headers $Headers
Invoke-RestMethod "$BaseUrl/v1/agent/jobs/$KnownJobId/artifacts" -Headers $Headers

$Artifacts = Invoke-RestMethod "$BaseUrl/v1/agent/jobs/$KnownJobId/artifacts" -Headers $Headers
if ($Artifacts.artifacts.Count -gt 0) {
  $ArtifactUrl = $Artifacts.artifacts[0].download_url
  Invoke-WebRequest "$BaseUrl$ArtifactUrl" -Method Head -Headers $Headers
}

Invoke-WebRequest "$BaseUrl/v1/agent/jobs/job_unknown" -Headers $Headers -SkipHttpErrorCheck
Invoke-WebRequest "$BaseUrl/v1/agent/jobs" -Headers @{ Authorization = "Bearer wrong-key" } -SkipHttpErrorCheck
```

Pending-result behavior when an active non-terminal job exists:

```powershell
$PendingJobId = "<NON_TERMINAL_JOB_ID>"
Invoke-WebRequest "$BaseUrl/v1/agent/jobs/$PendingJobId/result" -Headers $Headers -SkipHttpErrorCheck
```

Expected:

- Unknown job returns OpenAI-shaped 404.
- Unauthorized request returns 401.
- Pending result returns 409 with code `pending`.
- Failed job without result returns 409 with code `job_failed`.
- Research artifact download uses `/v1/chatgpt/files/{file_id}/{filename}`.

### 8.3 Browser Validation Checklist

1. Console startup
   - Preconditions: `bun` available; API started or planned offline test.
   - Steps: run `bun run --cwd apps/bridge-console dev`; open `http://127.0.0.1:5174`.
   - Expected: console loads without Svelte/runtime errors.
   - Evidence: screenshot and browser console log.

2. API base URL configuration
   - Preconditions: console running.
   - Steps: open Launch/Settings; set base URL to `http://127.0.0.1:8000/v1`; save.
   - Expected: setting persists after refresh.
   - Evidence: screenshot, localStorage value redacted.

3. API-key configuration
   - Preconditions: non-default test key available.
   - Steps: enter key; save; refresh.
   - Expected: requests use Authorization header, but UI must not render the key in clear text.
   - Evidence: screenshot with key redacted or after blocker fixed; Network request header inspected but not captured with value.

4. Agent Jobs navigation
   - Steps: click Agent Jobs nav.
   - Expected: URL hash becomes `#agent-jobs`; dashboard renders.
   - Evidence: screenshot.

5. Dashboard loading
   - Steps: open Agent Jobs while API reachable.
   - Expected: loading state then table or empty state.
   - Evidence: screenshot and `/v1/agent/jobs` response status.

6. Existing jobs displayed
   - Preconditions: current DB with 5 records.
   - Steps: load dashboard.
   - Expected: rows for succeeded chat/research, failed, and cancelled jobs.
   - Evidence: screenshot with job IDs partially redacted if desired.

7. Filters
   - Steps: apply `status=succeeded`, `type=chat`, `type=deep_research`, `error_code` where available.
   - Expected: backend query params match filters; rows narrow accordingly.
   - Evidence: Network request URLs and screenshots.

8. Pagination when enough jobs exist
   - Preconditions: more than 50 jobs or lowered test DB/page size not supported by UI.
   - Steps: create/preserve pagination-sized dataset; click Next/Previous.
   - Expected: cursor navigation works, no duplicate page timers.
   - Evidence: screenshots and network URLs with `cursor`.

9. Manual refresh
   - Steps: click Refresh.
   - Expected: one list request; last-updated changes.
   - Evidence: network log.

10. Automatic polling
   - Steps: keep dashboard open for 10+ seconds.
   - Expected: list refresh every ~5s; no overlapping requests.
   - Evidence: network timing.

11. Hidden-tab polling behavior
   - Steps: switch tab for 10+ seconds; return.
   - Expected: polling pauses while hidden and refreshes on return.
   - Evidence: network timing.

12. Job-detail navigation
   - Steps: click View on a row.
   - Expected: hash becomes `#jobs/<job_id>`; status, timeline, result/artifacts load.
   - Evidence: screenshot and network log.

13. Browser refresh on detail route
   - Steps: refresh browser while on `#jobs/<job_id>`.
   - Expected: same detail route reloads.
   - Evidence: screenshot after refresh.

14. Successful chat job
   - Preconditions: existing succeeded chat job.
   - Steps: open detail.
   - Expected: text result shown; raw normalized response available; no artifact success claim if none.
   - Evidence: screenshot.

15. Successful Deep Research job
   - Preconditions: existing succeeded research job.
   - Steps: open detail.
   - Expected: research result references markdown artifact; report is not re-summarized.
   - Evidence: screenshot.

16. Markdown artifact
   - Steps: open research job detail.
   - Expected: markdown preview loads as text, or safe download/open link appears.
   - Evidence: screenshot and artifact response.

17. Artifact download and HEAD
   - Steps: click artifact Open/Download; run HEAD smoke command.
   - Expected: file route returns success with shared Bearer key.
   - Evidence: browser download/network response and PowerShell output.

18. Cancelled queued job
   - Preconditions: queued-cancelled fixture or live job cancelled before running.
   - Steps: open detail.
   - Expected: cancelled state, no result, timeline shows cancellation.
   - Evidence: screenshot.

19. Cancelled running job
   - Preconditions: existing cancelled jobs with attempt-started events.
   - Steps: open detail for cancelled chat/research.
   - Expected: cancelled state, no result, timeline includes attempt/cancel events.
   - Evidence: screenshot.

20. Failed job
   - Preconditions: existing failed job.
   - Steps: open detail.
   - Expected: redacted error panel, no stored result panel.
   - Evidence: screenshot.

21. Unknown job
   - Steps: navigate to `#jobs/job_unknown`.
   - Expected: Job not found state.
   - Evidence: screenshot and 404 response.

22. Invalid API key
   - Steps: set wrong key; reload dashboard.
   - Expected: Unauthorized state.
   - Evidence: screenshot and 401 response with value redacted.

23. API server stopped
   - Steps: stop API; refresh dashboard/detail.
   - Expected: refresh failure/API unavailable state, last-known data preserved where present.
   - Evidence: screenshot and console/network error.

24. API server restarted
   - Steps: restart API; wait or manually refresh.
   - Expected: UI recovers and resumes polling.
   - Evidence: screenshot and network log.

25. Empty database behavior, if safely testable
   - Preconditions: throwaway admin DB, not current valuable DB.
   - Steps: start API with temp DB; open dashboard.
   - Expected: "No Agent Jobs exist yet."
   - Evidence: screenshot.

26. Narrow-window/table overflow behavior
   - Steps: resize to mobile/tablet width.
   - Expected: table scrolls horizontally; text does not overlap.
   - Evidence: screenshot.

27. Keyboard navigation
   - Steps: tab through filters, buttons, job rows.
   - Expected: focus visible; actions reachable.
   - Evidence: screen recording or checklist.

28. Status labels not relying only on color
   - Steps: inspect badges.
   - Expected: visible text labels and icons.
   - Evidence: screenshot.

29. No secret exposure
   - Steps: inspect all Agent Jobs pages and console shell with a non-default key.
   - Expected: no API key, Authorization header, cookies, captures, tokens, passphrases, or secret paths displayed.
   - Evidence: screenshot after blocker fixed; do not capture real secret values.

30. Regression check of existing console pages
   - Steps: visit Overview, Accounts, Test Lab, Limits, Docs, Library, opencode, Launch.
   - Expected: existing pages still render and core actions are not broken.
   - Evidence: screenshots or brief screen recording.

### 8.4 Restart and Persistence Tests

Safe tests:

- Restart API and confirm terminal jobs remain visible.
- Restart API and confirm research markdown artifact remains retrievable.
- Confirm UI resumes polling after API restart.
- Confirm `#jobs/<job_id>` detail URLs still work after API restart.
- Confirm the console does not own job state by closing/reopening the console and seeing the same backend records.

Use existing terminal jobs only unless explicitly creating disposable jobs. Do not run destructive cleanup or recovery tests against valuable live records.

## 9. Tests Currently Blocked

| Test | Missing prerequisite |
| --- | --- |
| Browser validation | API not currently reachable; live browser checklist not yet run. |
| Live API smoke tests | API not running/reachable at `127.0.0.1:8000`. |
| Active pending-result behavior | No queued/running job currently exists. |
| Queued-cancelled UI case | No confirmed queued-only cancelled job fixture in current DB. |
| Pagination browser test | Current DB has 5 jobs, below page size 50. |
| Formal no-secret screenshot evidence | Code-level blocker fixed; browser evidence still needs to be captured with a disposable key. |

## 10. Defects and Scope Gaps

| Severity | Evidence | Expected behavior | Actual behavior | Recommended action | Code changes required before browser testing? |
| --- | --- | --- | --- | --- | --- |
| RESOLVED | `App.svelte:18-19`, `App.svelte:1554-1556`, `App.svelte:1773-1841`, `App.svelte:2410-2420`, `App.svelte:2944-2953`, `App.svelte:2990-2992`, `App.svelte:3104-3106`, `App.svelte:4343-4345`, `Input.svelte` | UI never displays API keys or Authorization secrets. | Visible key fields are masked, snippets use `<API_KEY>`, and API-key inputs are password fields. | Browser checklist should verify this with a disposable key. | No. |
| RESOLVED | `npm.cmd --prefix apps/bridge-console run check`, `npm.cmd --prefix apps/bridge-console run build` | Console check/build must run. | Bun is still unavailable, but npm fallback ran safely against existing `node_modules`; both checks passed. | Prefer Bun when available; npm fallback is acceptable here because no install or lockfile rewrite occurred. | No. |
| TEST GAP | No bridge-console test files or package test script | Phase 1D UI behavior should be automated or covered by browser checklist. | No frontend automated test harness found. | Execute browser checklist; optionally add focused tests later if a frontend test pattern is established. | No, but required before acceptance. |
| TEST GAP | API not reachable; browser not run | Live smoke and browser validation against real records. | Static inspection only for UI behavior. | Start API and console, run smoke/browser tests. | Environment/runtime setup required. |
| MINOR | `AgentJobsPage.svelte:150-156` | Summary should avoid misleading omissions. | Summary cards show six statuses; accepted/validating/streaming/cancel_requested/expired are not carded though table/badges support them. | Consider including all statuses or adding "other visible statuses" count. | No, browser testing can proceed after blockers. |
| MINOR | `AgentJobsPage.svelte:162-168` | API-unavailable state should be explicit. | Network errors appear as "Agent Job refresh failed"; may be less clear than "Bridge unreachable". | Adjust copy if desired. | No. |
| OUT OF SCOPE | No submission/retry/SSE/queue controls | Phase 1D read-only only. | Not implemented. | Keep deferred to later phases. | No. |
| DOCUMENTATION DRIFT | `API_CONTRACT.md` lists `created_after`, `created_before`, `sort` as listing params; shipped parser lacks them (`agent_job_routes.py:616-653`) | Docs should distinguish proposed vs shipped. | UI correctly avoids them, but contract text still mentions them. | Small docs correction in a future documentation pass. | No. |

## 11. Security and Redaction Findings

Verified safe behavior:

- Agent Job backend serializers explicitly allowlist fields and do not expose filesystem storage keys in result payloads (`agent_job_routes.py:300-323`).
- Artifact serializer rebuilds download URLs and excludes filesystem paths (`agent_job_routes.py:336-348`).
- Repository event payloads are filtered through safe event keys (`agent_jobs.py:1519-1532`).
- Agent Jobs status JSON viewer defensively redacts token/key/cookie/path-like fields (`formatting.ts:3-109`).
- Capture contents were not read or displayed during this audit.

Previously blocking unsafe behavior now resolved:

- Top shell and Overview now call `maskedCredential(apiKey)` instead of rendering the configured value (`App.svelte:2990-2992`, `App.svelte:3104-3106`).
- Curl, CLI, Docker, Launch command, and opencode snippets now use `<API_KEY>` via `API_KEY_PLACEHOLDER` (`App.svelte:798-807`, `App.svelte:1554-1556`, `App.svelte:1773-1841`, `App.svelte:2410-2420`, `App.svelte:2944-2953`).
- Console API-key fields now use password inputs and a masked configured/not-configured status (`App.svelte:4343-4345`, `App.svelte:4603-4604`, `Input.svelte`).
- Real configured keys are still used internally for authenticated fetches and opencode injection requests (`App.svelte:932`, `App.svelte:1162`, `App.svelte:1334`, Agent Job components).

Static secret scan result: remaining `apiKey` references are acceptable internal uses for request headers, local state, localStorage, password input binding, or passing the key to Agent Job components for authenticated API calls. The only remaining visible `Authorization: Bearer` and `CHATGPT_API_KEY` strings use `<API_KEY>`.

## 12. Phase 1D Acceptance Criteria

Acceptance requires:

- `python -m compileall chatgpt_api` passes.
- Agent Job backend route/repository/facade tests pass, with only the known Windows `0o600` full-suite caveat if running on NTFS.
- Bridge-console check passes through Bun or a verified safe fallback.
- Bridge-console build passes through Bun or a verified safe fallback.
- Live API smoke tests pass against the migrated Agent Job DB.
- Browser validation checklist passes against real chat, Deep Research, failed, and cancelled records.
- No secret values are rendered in the console or captured in screenshots/logs.
- No Phase 2/3 features are claimed or invented.

Current status:

- Backend automated checks: mostly passed; full suite has known Windows caveat.
- Frontend automated checks: passed via `npm.cmd` fallback.
- Live API checks: not run.
- Browser checks: not run.
- Secret rendering: blocker fixed by static inspection and build/check validation.

## 13. Recommended Next Action

Run the Phase 1D live API smoke tests and browser validation checklist against the existing five Agent Job records.

## Appendix A -- Commands Run

```powershell
Get-Content -Raw 'C:\Users\Javit-PC-LLM\.codex\attachments\01c6f245-25f1-46c7-bc73-4a2f1560d9ef\pasted-text.txt'
Get-Content -Raw 'C:\Development\chatgpt-api\.agents\skills\capture-credentials-safety\SKILL.md'
rg --files
git status --short
git log --oneline -15
git diff --stat
Get-Content -Raw CLAUDE.md
Get-Content -Raw docs\agent_bridge\PROJECT_CONTEXT.md
Get-Content -Raw docs\agent_bridge\CURRENT_SYSTEM_ASSESSMENT.md
Get-Content -Raw docs\agent_bridge\TARGET_ARCHITECTURE.md
Get-Content -Raw docs\agent_bridge\IMPLEMENTATION_ROADMAP.md
Get-Content -Raw docs\agent_bridge\API_CONTRACT.md
Get-Content -Raw docs\agent_bridge\DATA_MODEL.md
Get-Content -Raw docs\agent_bridge\UI_WORKFLOW.md
Get-Content -Raw docs\agent_bridge\UI_WIREFRAMES.md
Get-Content -Raw docs\agent_bridge\DECISIONS.md
Get-Content -Raw docs\agent_bridge\SECURITY_MODEL.md
Get-Content -Raw docs\agent_bridge\STORAGE_DESIGN.md
rg -n "agent-jobs|jobs/|AgentJobsPage|AgentJobDetailPage|pages|hash|hashchange" apps\bridge-console\src\App.svelte
rg -n "fetch|listAgentJobs|getAgentJob|getAgentJobEvents|getAgentJobResult|getAgentJobArtifacts|URLSearchParams|status|type|cursor|limit" apps\bridge-console\src\lib\agent-jobs\api.ts apps\bridge-console\src\lib\agent-jobs\AgentJobsPage.svelte apps\bridge-console\src\lib\agent-jobs\AgentJobDetailPage.svelte
rg -n "def (handle_agent|list|submit|get|cancel)|/v1/agent|AgentJob|to_response|list_agent_jobs|record_agent|list_job|events|artifacts|attempt" chatgpt_api\api\agent_job_routes.py chatgpt_api\api\agent_jobs.py chatgpt_api\api\agent_job_coordinator.py chatgpt_api\api\openai_compat.py chatgpt_api\api\admin_store.py
python -m compileall chatgpt_api
python -m pytest tests/test_agent_jobs.py -q
python -m pytest tests/test_openai_compat.py -q
python -m pytest -q
bun run --cwd apps/bridge-console check
bun run --cwd apps/bridge-console build
docker compose config --quiet
git diff
rg -n "agent-jobs|AgentJobs|Agent Job|/v1/agent/jobs|cancelled|poll|events|artifacts|result" tests apps\bridge-console -g "*.py" -g "*.ts" -g "*.svelte" -g "*.spec.ts"
Get-Content -Raw apps\bridge-console\package.json
rg -n "apiKey|opencodeQuickCommand|CHATGPT_API_KEY|Authorization: Bearer|<API_KEY>|serverKey" apps\bridge-console\src\App.svelte apps\bridge-console\src\lib -g "*.svelte" -g "*.ts"
Get-Command bun -ErrorAction SilentlyContinue
Get-Command node -ErrorAction SilentlyContinue
Get-Command npm -ErrorAction SilentlyContinue
Get-Command npx -ErrorAction SilentlyContinue
Get-Command corepack -ErrorAction SilentlyContinue
bun --version
node --version
npm.cmd --version
npm.cmd --prefix apps/bridge-console run check
npm.cmd --prefix apps/bridge-console run build
rg -n "\{apiKey\}|\$\{apiKey\}|Authorization: Bearer|CHATGPT_API_KEY" apps/bridge-console/src
git diff --check
Invoke-WebRequest 'http://127.0.0.1:8000/health' -UseBasicParsing -TimeoutSec 2
```

Python inventory scripts were also run to count captures/jobs/artifacts without printing capture contents, cookies, tokens, API keys, or secret values.

## Appendix B -- Safe Test Data Inventory

```text
account_capture_present=true
account_capture_count=2
capture_content_displayed=false
admin_db_present=true
existing_agent_jobs=5
succeeded_chat_jobs>=1
succeeded_deep_research_jobs>=1
failed_jobs>=1
cancelled_jobs>=1
job_artifacts=1
research_markdown_artifact_present=true
api_key_value_displayed_by_audit=false
api_reachable_now=false
```

Safe job event summary:

```text
deep_research cancelled job: created, transition, transition, attempt_started, cancel_requested, attempt_finished, transition
chat cancelled job: created, transition, transition, attempt_started, cancel_requested, attempt_finished, transition
chat failed job: created, transition, transition, attempt_started, attempt_finished, transition
deep_research succeeded job: created, transition, transition, attempt_started, status_changed, attempt_finished
chat succeeded job: created, transition, transition, attempt_started, status_changed, attempt_finished
```

