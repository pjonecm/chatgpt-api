# Phase 1D Live API and Browser Validation

## 1. Executive Verdict

`PHASE 1D NOT ACCEPTED — DEFECTS FOUND`

Live API and browser validation ran on 2026-06-30 against the existing local
SQLite admin DB and the real bridge-console UI. The API started successfully,
the console loaded, the dashboard showed all five existing Agent Job records,
and chat/failed/cancelled/unknown states rendered safely.

Acceptance is blocked because the succeeded Deep Research job has a durable
research result but no associated artifact row. The required research result
and artifact checks fail live:

- `GET /v1/agent/jobs/job_aeb0a8d9ae66bf34adf354f5/result` returns `500`
  with `storage_failure`.
- `GET /v1/agent/jobs/job_aeb0a8d9ae66bf34adf354f5/artifacts` returns
  `200` with `artifacts: []`.
- Artifact `HEAD` could not run because no download URL exists.

## 2. Environment

```text
date=2026-06-30
workspace=C:\Development\chatgpt-api
api_base_url=http://127.0.0.1:8000
console_url=http://127.0.0.1:5174
api_key=disposable local validation key, value not recorded
admin_db=outputs/chatgpt-admin.sqlite
browser=in-app browser
node_package_manager=npm.cmd fallback, no install run
```

Repository state before validation:

```text
git status --short: existing Phase 1D/user dirty files plus untracked report/settings files
git log --oneline -10: tip 7ba20ed Add read-only agent job monitor
git diff --check: pass, line-ending warnings only
```

## 3. API Startup

The documented CLI startup was launched with a disposable local key:

```powershell
python -m chatgpt_api server start --api-key <DISPOSABLE_TEST_KEY>
```

The sandboxed background process did not persist across tool calls, so the API
was relaunched with approved unsandboxed background execution for browser
validation. `GET /health` with the disposable Bearer key returned HTTP 200 and
reported two configured accounts. No capture contents, cookies, bearer values,
or account secret material were displayed.

## 4. API Smoke Test Results

| Test | Result | Evidence |
| --- | --- | --- |
| 4.1 Health | PASS | HTTP 200, `ok=true`, two accounts reported. |
| 4.2 List jobs | PASS | HTTP 200, 5 jobs, `has_more=false`. |
| 4.3 Filter by status | PASS | `succeeded=2`, `failed=1`, `cancelled=2`; each filter returned only matching statuses. |
| 4.4 Filter by type | PASS | `chat=3`, `deep_research=2`; each filter returned only matching types. |
| 4.5 Select known jobs | PASS | Selected succeeded chat, succeeded Deep Research, failed chat, cancelled chat, cancelled Deep Research. |
| 4.6 Job status | PASS | Selected status endpoints returned HTTP 200, matching terminal states, timestamps, and no unsafe markers. |
| 4.7 Events | PASS | Event lists returned HTTP 200, ordered monotonic sequences, expected lifecycle events. |
| 4.8 Successful chat result | PASS | HTTP 200, `result_type=text`, text and normalized response present. |
| 4.9 Successful Deep Research result | FAIL | HTTP 500 `storage_failure`; artifacts endpoint returned zero artifacts. |
| 4.10 Artifact HEAD | FAIL | Blocked by missing artifact/download URL. |
| 4.11 Failed result behavior | PASS | HTTP 409, no fake result, no unsafe markers. |
| 4.12 Cancelled result behavior | PASS | HTTP 409 for cancelled chat and Deep Research, no fake result. |
| 4.13 Unknown job | PASS | HTTP 404. |
| 4.14 Unauthorized request | PASS | HTTP 401; configured key not echoed. |
| 4.15 Unsupported query behavior | PASS/DRIFT | `created_after=2026-01-01` was ignored and returned HTTP 200; not treated as supported. |

Safe selected inventory:

```text
succeeded_chat=job_c843a474e714c76bd7734e09, result_available=true, artifact_count=0, attempt_count=1
succeeded_deep_research=job_aeb0a8d9ae66bf34adf354f5, result_available=true, artifact_count=0, attempt_count=1
failed=job_ee34e8e4a93f9ca36ab13937, result_available=false, artifact_count=0, attempt_count=1
cancelled_chat=job_eaf6580007c67fbf48187e89, result_available=false, artifact_count=0, attempt_count=1
cancelled_deep_research=job_74775e96de3a7a46c6f7c8ae, result_available=false, artifact_count=0, attempt_count=1
```

## 5. Browser Test Results

| Scenario | Result | Notes |
| --- | --- | --- |
| 5.1 Console startup | PASS | Console loaded from Vite without visible crash. |
| 5.2 Configure API base URL | PASS | Set `http://127.0.0.1:8000/v1`; persisted across refresh. |
| 5.3 Configure API key | PASS | Password input and rendered status masked; body text did not contain the disposable key. |
| 5.4 Agent Jobs navigation | PASS | Agent Jobs navigation changed URL to `#agent-jobs`. |
| 5.5 Dashboard jobs | PASS | Five current records displayed with correct type/status labels and page-local summary. |
| 5.6 Filters | PARTIAL PASS | Status and type filters matched backend. Error-code input was visible, but browser automation could not focus the fifth text input reliably; backend error-code filtering passed via smoke/static route mapping. |
| 5.7 Page-local job search | PARTIAL | Label clearly states job-ID search is local. Automation could not complete the text-input focus step reliably. |
| 5.8 Manual refresh | PASS | Refresh control rendered and page updated timestamp changed during validation. |
| 5.9 Automatic polling | PASS | Dashboard recovered and remained updated after waiting beyond one poll interval. |
| 5.10 Hidden-tab behavior | NOT RUN | Not completed because Phase 1D was already blocked by the research artifact defect. |
| 5.11 Successful chat detail | PASS | `#jobs/<job_id>` route showed succeeded chat, timeline, result text/normalized response; no artifact falsely shown. |
| 5.12 Detail route refresh | PASS | Hard refresh on chat detail route reloaded the same job detail. |
| 5.13 Successful Deep Research detail | FAIL | Detail route showed succeeded research but surfaced storage failure/no markdown artifact. |
| 5.14 Artifact preview/download | FAIL | No artifact row/download URL exists. |
| 5.15 Failed job | PASS | Failed status and `internal_error` rendered safely, no fake result. |
| 5.16 Cancelled chat job | PASS | Cancelled status and cancellation lifecycle events rendered; no result. |
| 5.17 Cancelled Deep Research job | PASS | Cancelled status and cancellation lifecycle events rendered; no false artifact. |
| 5.18 Unknown job | PASS | `#jobs/job_unknown` rendered job-not-found state without crash. |
| 5.19 Invalid API key | PASS | Unauthorized state rendered, zero rows exposed, key not echoed; valid key restored. |
| 5.20 API unavailable | PASS | Dashboard showed failed refresh/offline state without key exposure. |
| 5.21 Restart persistence | PARTIAL PASS | Five job records survived API restart; research artifact remained missing and result still returned 500. |
| 5.22 Responsive layout | PASS | Narrow 430px viewport kept navigation usable and table horizontally scrollable. |
| 5.23 Keyboard accessibility | PARTIAL PASS | Buttons, inputs, selects, and job actions were focusable elements; full manual Tab/Shift+Tab traversal not completed after blocking defect. |
| 5.24 Existing page regression | PASS | Overview, Accounts, Test Lab, Limits, Docs, Library, opencode, and Launch rendered; no disposable key visible. |

## 6. Security and Redaction Validation

Passed for observed API and browser surfaces:

- No real API key value was printed in final evidence.
- Console rendered `********` or `<API_KEY>` placeholders rather than the
  configured disposable key.
- Unauthorized response did not echo the configured key.
- Status/events/result smoke scans did not find `Authorization`, `Bearer`,
  `cookie`, `sentinel`, `proof`, `conduit`, `secrets/accounts`, or local
  output path markers in selected job payloads.
- No raw capture file was read or displayed.

## 7. Restart and Persistence Results

API restart succeeded. After restart:

```text
jobs=5
statuses=cancelled=2,failed=1,succeeded=2
types=deep_research=2,chat=3
dashboard_rows=5
```

The Deep Research defect persisted after restart:

```text
GET /v1/agent/jobs/job_aeb0a8d9ae66bf34adf354f5/result -> HTTP 500
```

## 8. Regression Results

Existing console pages rendered and did not display the disposable key:

```text
Overview=pass
Accounts=pass
Test Lab=pass
Limits=pass
Docs (#api-docs)=pass
Library (#storage)=pass
opencode=pass
Launch (#settings)=pass
```

## 9. Blocked Optional Tests

```text
queued_only_cancellation=not run; no queued-only cancelled record present
pending_result_ui=not run; no queued/running job present
pagination=not run; live DB has 5 jobs, below page size
hidden_tab_polling=not completed; validation already blocked by required artifact defect
full_keyboard_traversal=partial only; validation already blocked by required artifact defect
```

## 10. Defects Found

### BLOCKER - Deep Research Success Has No Downloadable Artifact

Test numbers: 4.9, 4.10, 5.13, 5.14, 5.21.

Expected behavior: a succeeded Deep Research job returns `result_type=research`,
lists a markdown artifact with `text/markdown` content type, and provides an
existing `/v1/chatgpt/files/...` download URL that responds to `HEAD`.

Actual behavior:

```text
GET /v1/agent/jobs/job_aeb0a8d9ae66bf34adf354f5/result
-> HTTP 500 storage_failure
message="job research artifact is missing or invalid"

GET /v1/agent/jobs/job_aeb0a8d9ae66bf34adf354f5/artifacts
-> HTTP 200 {"artifacts":[]}
```

Evidence:

```text
agent_jobs.status=succeeded
agent_jobs.result_id=result_4496e5997bd62fe4f695d6d8
job_results.result_type=research
artifacts rows for job=0
artifacts table rows=0
```

Severity: `BLOCKER`.

Root cause: the existing live DB/result state has a research result without a
registered artifact row. This may be a persistence/association defect in the
Deep Research job execution path or a test-data drift issue from prior live
runs. The validation task forbids manual DB alteration, so it was not repaired
during this run.

Acceptance blocked: yes.

Recommended minimal fix: fix the Deep Research job artifact registration or
restore a valid associated artifact through the real execution path, then
rerun the affected API and browser tests. Do not manually patch the live DB as
the acceptance path.

### TEST GAP - Browser Hidden-Tab Polling Not Completed

Expected behavior: dashboard polling pauses while hidden and resumes without a
request burst.

Actual behavior: not completed because the required Deep Research artifact
acceptance criterion already failed.

Severity: `TEST GAP`; acceptance remains blocked by the artifact defect above.

### TEST GAP - Full Browser Error-Code Input and Job-ID Search Interaction

Expected behavior: error-code filter and page-local job search work in browser.

Actual behavior: controls were visible and backend/static mapping passed, but
the browser automation could not reliably focus the fifth text input after
filter changes.

Severity: `TEST GAP`; acceptance remains blocked by the artifact defect above.

## 11. Acceptance Criteria

Required criteria not met:

- Successful Deep Research result did not return HTTP 200.
- Markdown artifact was not listed.
- Artifact `HEAD` could not run.
- Research detail did not show a markdown preview/download.
- Restart persistence preserved jobs but not a valid research artifact.

Required criteria met or partially met:

- API startup, health, list, filters, selected status/events, chat result,
  failed result, cancelled result, unknown job, unauthorized request.
- Dashboard display of real records.
- Chat, failed, cancelled, unknown detail states.
- API unavailable and recovery state.
- Controlled polling and responsive layout basics.
- Existing console page no-secret regression.

## 12. Final Verdict

`PHASE 1D NOT ACCEPTED — DEFECTS FOUND`

## Appendix A - Commands Run

```powershell
Get-Content -LiteralPath C:\Users\Javit-PC-LLM\.codex\attachments\af94c680-4a72-4a8b-9861-3ead2a2c5647\pasted-text.txt
Get-Content -LiteralPath AGENTS.md
Get-Content -LiteralPath docs\reports\PHASE_1D_STATUS_AND_TEST_PLAN.md
Get-Content -LiteralPath docs\agent_bridge\API_CONTRACT.md
Get-Content -LiteralPath docs\agent_bridge\UI_WORKFLOW.md
Get-Content -LiteralPath docs\agent_bridge\UI_WIREFRAMES.md
Get-Content -LiteralPath docs\agent_bridge\SECURITY_MODEL.md
git status --short
git log --oneline -10
git diff --check
python -m chatgpt_api server start --api-key <DISPOSABLE_TEST_KEY>
Invoke-RestMethod http://127.0.0.1:8000/health -Headers <redacted>
Invoke-RestMethod http://127.0.0.1:8000/v1/agent/jobs?limit=50 -Headers <redacted>
curl.exe -s -i -H <redacted> http://127.0.0.1:8000/v1/agent/jobs/job_aeb0a8d9ae66bf34adf354f5/result
curl.exe -s -i -H <redacted> http://127.0.0.1:8000/v1/agent/jobs/job_aeb0a8d9ae66bf34adf354f5/artifacts
npm.cmd --prefix apps/bridge-console run dev
```

Browser validation used the in-app browser at `http://127.0.0.1:5174` and did
not save screenshots containing credentials.

## Appendix B - Evidence Inventory

```text
safe_api_summary=health/list/filter/status/events/chat-result/terminal-result/unauthorized/unknown checks
safe_browser_summary=dashboard/detail/outage/recovery/responsive/regression observations
secret_evidence=none captured
raw_captures_read=false
database_modified=false
manual_artifact_repair=false
commit_created=false
```

