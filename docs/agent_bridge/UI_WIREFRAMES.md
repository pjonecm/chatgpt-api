# UI Wireframes â€” Agent Job Bridge Console

> Low-fidelity text/Mermaid wireframes to lock workflow, information
> hierarchy, API requirements, states, actions, navigation. Not polished
> assets. Extends `apps/bridge-console`.
>
┌─ Job job_01AB…  [Running]  [Back] [Refresh]────────────┐
> monitoring with shipped endpoints (`#agent-jobs`, `#jobs/<job_id>`).
> Submit Test, Queue, Storage, and Integration wireframes are future/reference
┌─ Job job_01AB…  [Running]  [Back] [Refresh]────────────┐

## Navigation shell

```text
â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
┌─ Job job_01AB…  [Running]  [Back] [Refresh]────────────┐
â”‚ Overview | Agent Jobs | Accounts | Artifacts | Settings       â”‚
┌─ Job job_01AB…  [Running]  [Back] [Refresh]────────────┐
â”œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”¤
â”‚                                                                â”‚
â”‚                    < page content >                            â”‚
â”‚                                                                â”‚
â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
```

┌─ Job job_01AB…  [Running]  [Back] [Refresh]────────────┐

## 1. Agent Jobs Dashboard

```text
â”Œâ”€ Agent Jobs â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
â”‚ Summary:  [Queued 3] [Running 1] [Retry 0] [Succeeded 42]      â”‚
â”‚           [Failed 2] [Cancelled 1]  Oldest queued: 4m  Avg: 38sâ”‚
â”‚                                                                â”‚
â”‚ Filters: [search____] [statusâ–¾] [typeâ–¾] [modelâ–¾] [accountâ–¾]    â”‚
┌─ Job job_01AB…  [Running]  [Back] [Refresh]────────────┐
â”‚                                                                â”‚
â”‚ â”Œâ”€â”€Jobâ”€â”€â”€â”€â”€â”€â”¬ClientReqâ”€â”€â”¬Typeâ”€â”€â”¬Statusâ”€â”€â”¬Modelâ”€â”€â”¬Acctâ”€â”€â”¬Attâ”¬â”€ â”‚
â”‚ â”‚ job_01ABâ€¦ â”‚ run-123    â”‚ chat â”‚ Running â”‚ auto  â”‚ main â”‚ 1 â”‚ â”‚
â”‚ â”‚ job_01CDâ€¦ â”‚ camp-77-1  â”‚ img  â”‚ Succ.   â”‚ gpt-â€¦ â”‚ img  â”‚ 1 â”‚ â”‚
â”‚ â”‚ job_01EFâ€¦ â”‚ research42 â”‚ res  â”‚ Failed  â”‚ deepâ€¦ â”‚ res  â”‚ 3 â”‚ â”‚
â”‚ â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜ â”‚
â”‚  â† 1 2 3 â†’    showing 1â€“50 of 142        [auto-refresh 5s â—]    â”‚
â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
```

States: loading skeleton; empty "No jobs yet"; error banner;
no-results "No jobs match filters"; API-unavailable "Bridge unreachable".

## 2. Submit Text Job (future, not Phase 1 UI)

```text
â”Œâ”€ Submit Test Â· Chat â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
â”‚ Mode: (â€¢) Asynchronous job   ( ) Synchronous (test-lab)         â”‚
â”‚ Model: [auto â–¾]   Stream: [ ]                                  â”‚
â”‚ System: [_____________________________________________]         â”‚
â”‚ User:   [_____________________________________________]         â”‚
â”‚         [_____________________________________________]         â”‚
â”‚ Prior messages: (optional)  [+ add turn]                       â”‚
â”‚ Client request id: [agent-run-123]                             â”‚
â”‚ Idempotency key:   [agent-run-123-step-4]                      â”‚
â”‚                                            [Reset] [Submit â–¸]  â”‚
â”‚ â†’ on accept: "Submitted job_01â€¦" [Open job â†’]                  â”‚
┌─ Job job_01AB…  [Running]  [Back] [Refresh]────────────┐
â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
```

## 3. Submit Image Job (future, not Phase 1 UI)

```text
â”Œâ”€ Submit Test Â· Image Generation â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
â”‚ Model: [gpt-image-1 â–¾]   Size: [1024x1024 â–¾]                   â”‚
â”‚ Prompt: [_____________________________________________]         â”‚
â”‚ Client request id: [campaign-77-frame-1]                       â”‚
â”‚ Idempotency key:   [campaign-77-frame-1-v1]                    â”‚
â”‚                                            [Reset] [Submit â–¸]  â”‚
â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
```

┌─ Job job_01AB…  [Running]  [Back] [Refresh]────────────┐
("image/png Â· 1.2 MiB âœ“"; "image/heic Â· unsupported"), up to 10.

## 4. Job Detail

```text
┌─ Job job_01AB...  [Running]  [Back] [Refresh]────────────┐
â”‚ Client req: run-123   Idempotency: agâ€¦123-step-4 (partial)    â”‚
â”‚ Created 12:00 Â· Queued 12:00 Â· Started 12:01 Â· (running)      â”‚
â”‚                                                                â”‚
┌─ Job job_01AB…  [Running]  [Back] [Refresh]────────────┐
â”‚ â–¸ Attempts  #1 main-free Â· running                             â”‚
â”‚ â–¸ Request payload (redacted)   {model, messages, â€¦}  [copy]   â”‚
â”‚ â–¸ Inputs   (none)                                              â”‚
â”‚ â–¸ Result   (pendingâ€¦ / or text + raw response [copy])         â”‚
â”‚ â–¸ Artifacts  [icon.png â–¸ preview] [download]                  â”‚
â”‚ â–¸ Error    (none / redacted code + message)                   â”‚
â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
```

```mermaid
flowchart LR
    A[created]-->B[queued]-->C[attempt_started]-->D[delta x12]
    D-->E{succeeded?}
    E-->|yes|F[succeeded]
    E-->|retryable|G[retry_wait]-->B
┌─ Job job_01AB…  [Running]  [Back] [Refresh]────────────┐
```

## 5. Queue and Execution Status (future, not Phase 1 UI)

```text
â”Œâ”€ Queue & Execution â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
â”‚ Coordinator: in-process Â· pid 1234 Â· last heartbeat 2s ago     â”‚
â”‚ [Queued 3] [Running 1] [Retry 0]  Oldest queued: 4m            â”‚
â”‚ Active job: job_01ABâ€¦ (chat, main-free)                        â”‚
â”‚ Per-account concurrency: main-free 1/1 Â· image-pro 0/1         â”‚
â”‚ Per-capacity: chat 1/1 Â· image 0/1 Â· research 0/1 Â· upload 0/1 â”‚
â”‚ Waiting for capacity: 0                                        â”‚
â”‚ Stale-running: 0      Restart recoveries today: 1              â”‚
â”‚ Recent failures: job_01EFâ€¦ (chatgpt_auth_or_browser_challenge) â”‚
â”‚ Last success: 38s ago                                          â”‚
â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
```

## 6. Storage and Artifact Status (future, not Phase 1 UI)

```text
â”Œâ”€ Storage & Artifacts â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
â”‚ Artifacts: 128 (image 96 Â· research 32)   Usage: ~1.4 GiB      â”‚
â”‚ Input storage: 12 MiB   Result storage: 8 MiB                  â”‚
â”‚ Expired (pending cleanup): 4   Missing files: 0   Orphans: 0   â”‚
â”‚ Failed cleanups: 0   Last cleanup: 2026-06-27 03:00            â”‚
┌─ Job job_01AB…  [Running]  [Back] [Refresh]────────────┐
┌─ Job job_01AB…  [Running]  [Back] [Refresh]────────────┐
â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
```

┌─ Job job_01AB…  [Running]  [Back] [Refresh]────────────┐

```text
â”Œâ”€ Agent Integration â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
â”‚ Base URL:        http://<PRODUCTION_HOST>:8000/v1              â”‚
â”‚ Auth header:     Authorization: Bearer <API_KEY>               â”‚
â”‚ Submit job:      POST /v1/agent/jobs                           â”‚
â”‚ List jobs:       GET  /v1/agent/jobs                           â”‚
â”‚ Status:          GET  /v1/agent/jobs/{job_id}                  â”‚
â”‚ Result:          GET  /v1/agent/jobs/{job_id}/result           â”‚
┌─ Job job_01AB…  [Running]  [Back] [Refresh]────────────┐
â”‚ Events:          GET  /v1/agent/jobs/{job_id}/events           â”‚
â”‚ Artifacts:       GET  /v1/agent/jobs/{job_id}/artifacts        â”‚
â”‚                                                                â”‚
┌─ Job job_01AB…  [Running]  [Back] [Refresh]────────────┐
â”‚ Limits: 25 MiB request Â· 20 MiB/image Â· 10 images              â”‚
â”‚ Current Agent Jobs: chat, deep_research                        â”‚
┌─ Job job_01AB…  [Running]  [Back] [Refresh]────────────┐
┌─ Job job_01AB…  [Running]  [Back] [Refresh]────────────┐
â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
```

┌─ Job job_01AB…  [Running]  [Back] [Refresh]────────────┐

```mermaid
graph TD
    Page[AgentJobs page] --> Nav
    Page --> Summary[JobSummaryCards]
    Page --> Filters[JobFilters]
    Page --> Table[JobTable]
    Table --> Row[JobRow]
    Row --> Badge[JobStatusBadge]
    Row --> TypeBadge[JobTypeBadge]
    Row --> Actions[view/cancel]
    Page --> Poll[PollingStatus]
┌─ Job job_01AB…  [Running]  [Back] [Refresh]────────────┐
```

## State matrix (dashboard)

| State | Trigger | Render |
| --- | --- | --- |
┌─ Job job_01AB…  [Running]  [Back] [Refresh]────────────┐
| empty | 0 jobs total | "No jobs yet" |
| no-results | filters match 0 | "No jobs match filters" + Clear |
| error | fetch non-2xx | redacted banner + retry |
| auth | 401 | "Unauthorized â€” check key in Settings" |
| unavailable | network/timeout | "Bridge unreachable" + stale data |
┌─ Job job_01AB…  [Running]  [Back] [Refresh]────────────┐
