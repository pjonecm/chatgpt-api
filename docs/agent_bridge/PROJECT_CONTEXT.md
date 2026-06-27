# Project Context — AI Agent → ChatGPT API Bridge

> Design only. No implementation. Grounded in repository evidence on 2026-06-27.
> When code and this document disagree, trust the code (`CLAUDE.md` §0).
> This is **not** the official OpenAI API. Use the wording "OpenAI-shaped" /
> "Chat Completions-style".

## 1. Purpose

Extend the existing `chatgpt-api` local bridge with a **durable asynchronous
agent-job layer** so external AI agents, workflow systems, and applications
can submit text, multimodal, image-generation, image-edit, vision, and Deep
Research requests; have them processed through the existing ChatGPT Web
provider; track them durably across process/container restarts; and retrieve
results, events, and artifacts reliably. The package also defines the
operator UI to submit, monitor, inspect, diagnose, and manage those jobs.

## 2. Problem statement

The current bridge is **request/response oriented** (`CLAUDE.md` §7). Long
jobs (image generation, Deep Research) can run for minutes to ~90 minutes
(`CHATGPT_WEB_TIMEOUT=5400`). Operation state is **in-memory only**
(`_CHATGPT_OPERATIONS` dict, `openai_compat.py:190`) and is **lost on
restart** (`docs/OPENAI_COMPATIBILITY.md` "Cancellation"). AI agents and
workflow systems that retry automatically have **no idempotency**, **no
durable queue**, and **no reliable result-retrieval contract**. They cannot
safely submit a Deep Research job, crash, and resume polling.

## 3. Users

- **Agent authors** integrating an external AI agent/workflow runtime against
  the bridge as a backend.
- **App developers** using the bridge as a backend for a small product or
  internal tool.
- **Operators** running a private LAN bridge, monitoring and diagnosing jobs.
- **Integration testers** submitting test jobs through the console before
  wiring a real agent.

## 4. Calling systems

External AI agents, local agent runtimes, workflow automation, internal
applications, LAN services, OpenAI-compatible clients, custom HTTP clients,
scheduled processes, multi-agent orchestration frameworks.

## 5. Current capability (verified)

- OpenAI-shaped `/v1` routes: chat (sync + SSE), images/generations,
  images/edits, vision, Deep Research (`docs/OPENAI_COMPATIBILITY.md`).
- Account routing with failover/round-robin/weighted/quota-aware/random
  (`AccountRouter`, `openai_compat.py:80`).
- Per-account + per-feature `BoundedSemaphore` throttles
  (`_ACCOUNT_LIMITERS:225`, `_FEATURE_LIMITERS:228`).
- Artifact storage + SQLite metadata (`admin_store.py`, `artifacts` table).
- Encrypted-at-rest captures (`crypto.py`, Fernet `enc:v1:`).
- **In-memory** operation inspect/cancel (`_CHATGPT_OPERATIONS:190`).
- Bridge console (Svelte 5 SPA, hash-routed, `apps/bridge-console`).

## 6. Target capability

A durable, restart-safe, idempotent asynchronous job API **additive** to the
existing synchronous routes, plus an operator console surface for monitoring,
test submission, and diagnostics. See `TARGET_ARCHITECTURE.md`,
`API_CONTRACT.md`, `UI_WORKFLOW.md`.

## 7. Scope

- **In scope:** durable `AgentJob` schema + state machine; job submission /
  list / status / result / cancel endpoints; local file + SQLite storage;
  in-process coordinator with restart recovery; idempotency; operator UI for
  monitoring + test submission; reuse of existing provider/router/artifact
  infrastructure.
- **Out of scope (Phase 1):** Redis, PostgreSQL, MinIO/S3, separate worker
  containers, multi-tenant RBAC, signed artifact URLs, per-client keys,
  Kubernetes. These are deferred with explicit triggers
  (`STORAGE_DESIGN.md`, `SECURITY_MODEL.md`).

## 8. Non-goals

- Not a hosted multi-tenant SaaS.
- Not replacing the synchronous OpenAI-shaped routes.
- Not redesigning the ChatGPT provider transport.
- Not executing tools (the bridge never executes client tools — `CLAUDE.md`
  §7).
- Not claiming security guarantees not enforced in code.

## 9. Terminology

- **Agent job** — a durable asynchronous unit of work submitted by an external
  caller.
- **Operation** — the existing in-memory runtime record for a long provider
  call (`_ChatGPTOperation`).
- **Attempt** — one provider invocation for a job (retries create attempts).
- **Artifact** — a generated file (image/research) registered in the
  `artifacts` table with a `file_id` download URL.
- **Idempotency key** — caller-supplied deduplication token.
- **OpenAI-shaped** — API shape compatible with common OpenAI clients, not
  the official API.

## 10. Architectural principles

1. **Additive, not replacing** — synchronous routes stay unchanged.
2. **Reuse infrastructure** — provider registry, `AccountRouter`,
   `BoundedSemaphore` limits, `BridgeAdminStore`, artifact download path.
3. **Provider-first** — provider quirks stay in `providers/chatgpt/`; API
   shapes stay in `api/` (`docs/ARCHITECTURE.md`).
4. **SQLite + local files first** — no new infra in Phase 1.
5. **Metadata in SQLite, binaries on disk** — never store large blobs in
   SQLite.
6. **Effectively-once** execution via idempotency + lease/recovery.
7. **Backend is the security boundary** — the UI is never a security control.
8. **No secret exposure** — captures/cookies/tokens never returned or logged.

## 11. Known constraints

- Single shared Bearer key; no RBAC; no tenant isolation (`CLAUDE.md` §8).
- CORS `*` (`http_utils.py:34`).
- Operation state in-memory, lost on restart.
- Token usage returns zero placeholders (`CLAUDE.md` §12).
- Captures expire ~10 days; not repairable locally.
- `openai_compat.py` is ~5,580 lines, intentionally monolithic; no
  speculative splits (`CLAUDE.md` §10, §17).
- Windows `0o600` key-file permission is not enforced on NTFS
  (`CLAUDE.md` §17).

## 12. Success criteria

- An agent can submit a job, receive `job_id` + status URL, and retrieve the
  result after a process restart.
- Duplicate submissions with the same idempotency key return the original
  job, not a duplicate.
- A job running at crash time is recovered to a safe state on restart (not
  silently stuck in `running`).
- Operators can list, filter, inspect, and cancel jobs in the console.
- Existing synchronous routes, CLI, console, and character-game integration
  remain unchanged and tests stay green.
- No real credential is ever logged, returned, or committed.

## 13. Related documents

- `CURRENT_SYSTEM_ASSESSMENT.md` — verified current state.
- `TARGET_ARCHITECTURE.md` — target design.
- `API_CONTRACT.md` — request/response contracts.
- `DATA_MODEL.md` — schema + state machine.
- `STORAGE_DESIGN.md` — local storage + future adapters.
- `SECURITY_MODEL.md` — security reality + progression.
- `UI_WORKFLOW.md` / `UI_WIREFRAMES.md` — operator UI.
- `IMPLEMENTATION_ROADMAP.md` — phased plan.
- `DECISIONS.md` — ADRs.
