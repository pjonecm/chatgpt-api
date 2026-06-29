# Phase 1C.5 Live E2E Verification

Date: 2026-06-29
Environment: Windows, `C:\Development\chatgpt-api`
Implementation baseline: `eeac481` (`Phase 1C.4 execute deep research agent jobs`)
Documentation closeout commit tested: `b2fdc94`

## Result

**Accepted.** A real usable ChatGPT account capture was added under the
ignored `secrets/accounts/` tree and verified through the running local API.
No capture contents, cookies, bearer tokens, sentinel/proof tokens, key
material, or decrypted capture text were printed or written to this report.

Verified account summary:

| Alias | Verify result | Plan metadata | Research quota metadata | Image quota metadata |
| --- | --- | --- | --- | --- |
| `main-free` | `ok=yes` | `plus` | `25` | `120` |

## Local Safety Checks

| Check | Result |
| --- | --- |
| `Test-Path .\secrets\accounts\main-free\chatgpt-request.txt` | `True` |
| `git check-ignore -v secrets/accounts/main-free/chatgpt-request.txt secrets/accounts/.master.key outputs/chatgpt-admin.sqlite` | All checked paths are ignored by `.gitignore` |
| `git status --short` | No tracked secret/output/env files; unrelated local untracked files remain outside this report |
| Capture content inspection | Not performed |

## Live Scenario Results

| Scenario | Result | Evidence |
| --- | --- | --- |
| Verify saved capture/account | Passed | `python -m chatgpt_api admin account verify --account main-free --base-url http://127.0.0.1:8000/v1 --api-key local-dev-key` returned `ok=yes` |
| Submit non-streaming `chat` Agent Job and poll to terminal | Passed | `job_c843a474e714c76bd7734e09` reached `succeeded` on attempt 1 |
| Fetch persisted chat result | Passed | Result route returned `result_type=text` |
| Submit `deep_research` Agent Job and poll to terminal | Passed | `job_aeb0a8d9ae66bf34adf354f5` reached `succeeded` on attempt 1 |
| Fetch persisted Deep Research result | Passed | Result route returned `result_type=research` |
| Verify Deep Research markdown artifact association | Passed | Artifact route returned 1 artifact for the research job |
| Verify artifact download endpoint | Passed | `HEAD` on the normalized local artifact URL returned `200`, `text/markdown`, length `1591` |
| Idempotency duplicate replay | Passed | Reposting the same chat request with the same idempotency key returned original job `job_c843a474e714c76bd7734e09` |
| Cancel queued/non-running job | Passed | `job_eaf6580007c67fbf48187e89` moved from `cancel_requested` to terminal `cancelled` |
| Cancel running Deep Research job | Passed | `job_74775e96de3a7a46c6f7c8ae` was observed in `running`, cancellation was issued, and final status was `cancelled` |
| Unsupported image Agent Job fails closed | Passed | `image_generation` submission returned HTTP `400 Bad Request` |
| Unsupported `stream=true` Agent Job fails closed | Passed with note | Submission queued `job_ee34e8e4a93f9ca36ab13937`, then execution failed terminally with `error_code=internal_error` and message `stream=true agent jobs are not supported`; no result was exposed |
| Secret/capture leakage audit | Passed for this run | Commands and report contain only aliases, status metadata, job IDs, file IDs, filenames, byte counts, and HTTP status metadata |

## Deterministic Validation Reference

The Phase 1C.4 closeout validation remained the deterministic baseline for
this live gate:

| Command | Result |
| --- | --- |
| `python -m compileall chatgpt_api` | Passed |
| `python -m pytest tests/test_agent_jobs.py -q` | `96 passed` |
| `python -m pytest tests/test_agent_job_routes.py -q` | `61 passed` |
| `python -m pytest tests/test_agent_job_coordinator.py -q` | `24 passed` |
| `python -m pytest tests/test_agent_job_text_execution.py -q` | `6 passed` |
| `python -m pytest tests/test_agent_job_research_execution.py -q` | `3 passed` |
| `python -m pytest tests/test_openai_compat.py -q` | `88 passed` |
| `docker compose config --quiet` | Exit 0; Docker warned that `C:\Users\Javit-PC-LLM\.docker\config.json` was inaccessible |
| `python -m pytest -q` | `379 passed, 1 failed` with the documented Windows-only `0o600` permission assertion mismatch |

## Acceptance Decision

Phase 1C.5 is **accepted** for this workspace as of 2026-06-29. The Phase 1
read-only Agent Job monitoring UI gate may now proceed, with the same locked
scope: read-only monitoring using shipped endpoints only, no submission UI,
no queue/storage summary endpoints, no new auth, and no exposure of capture
material.
