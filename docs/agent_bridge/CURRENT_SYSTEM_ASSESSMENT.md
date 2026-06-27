# Current System Assessment — AI Agent → ChatGPT API Bridge

> Verified against code on 2026-06-27. File:line references are the evidence.
> Trust the code over docs when they conflict (`CLAUDE.md` §0).

## 1. Verified architecture

- **Backend:** Python ≥ 3.11 stdlib `http.server.ThreadingHTTPServer` +
  `BaseHTTPRequestHandler` in `openai_compat.py`. No web framework. SSE
  hand-rolled. Entry `chatgpt-api server start` = `chatgpt_api.cli:main`.
- **Provider layer:** `core/provider.py` defines `AIProvider` (abstract
  `stream_chat`, `chat`, `generate_image`); `core/registry.py` defines
  `ProviderRegistry`/`default_registry`. ChatGPT Web is the first provider
  (`providers/chatgpt/provider.py`).
- **Core types:** `core/types.py` — `ChatRequest`, `ChatDelta`, `ChatResponse`,
  `ImageRequest`, `ImageInput`, `ImageAsset`, `ImageResponse`,
  `ProviderCapabilities`, `Message`/`ContentPart` (text/image_url/image_bytes).
- **Config:** `api/config.py` — `OpenAICompatConfig` (frozen dataclass,
  `slots=True`): account, accounts, accounts_dir, host, port, api_key,
  account_strategy, model_fallback, temporary_chat, image/research output
  dirs, admin_db_path, public_base_url, web_timeout, per-feature concurrency
  strings.
- **DB:** stdlib `sqlite3` via `BridgeAdminStore` (`admin_store.py`).
- **Frontend:** two apps — `apps/bridge-console` (Svelte 5 SPA, nginx),
  `apps/character-game` (SvelteKit node).

## 2. Existing request flows

| Route | Handler (openai_compat.py) | Notes |
| --- | --- | --- |
| `POST /v1/chat/completions` | `do_POST` | sync + SSE; tool bridge via `prompts.py`; Deep Research via `chatgpt-deep-research` alias |
| `POST /v1/images/generations` | `do_POST` | `n` fixed to 1; saves artifact; returns `chatgpt_operation_id` |
| `POST /v1/images/edits` | `do_POST` | 1–10 source images via `image_inputs.py`; one output image |
| `POST /v1/chatgpt/vision` | `do_POST` | OCR/describe; up to 10 images; returns text, no artifact |
| `GET /v1/chatgpt/operations/{id}` | `_get_chatgpt_operation` (~570) | reads in-memory `_CHATGPT_OPERATIONS` |
| `POST /v1/chatgpt/operations/{id}/cancel` | `_cancel_chatgpt_operation` (~589) | sets `cancel_requested`, best-effort provider stop |
| `GET/HEAD /v1/chatgpt/files/{file_id}/{filename}` | `do_GET`/`do_HEAD` | resolves `file_id` from in-memory registry then admin DB |
| `/v1/chatgpt/admin/*` | `do_POST`/`do_GET` | operator endpoints (status, accounts, captures, settings, artifacts, opencode, test) |

Per-path detail (verified):

- **Auth:** `authorize()` (`http_utils.py:11`) — single shared Bearer; no
  key ⇒ open. Same gate for public + admin routes.
- **CORS:** `send_cors_headers()` (`http_utils.py:33`) sends
  `Access-Control-Allow-Origin: *` on every response; also hardcoded at
  `openai_compat.py:2273`.
- **Account selection:** `AccountRouter.order()` (`openai_compat.py:91`);
  strategies at `ACCOUNT_STRATEGIES:195`. Model-aware filtering at
  `_account_order_for_model:691`.
- **Concurrency:** `BoundedSemaphore` per `(feature, account)` at
  `_FEATURE_LIMITERS:228` and per-account at `_ACCOUNT_LIMITERS:225`;
  acquired via `_with_provider_feature_limits:670` and
  `_with_provider_account_limit:638`.
- **Preflight quota:** `_account_order_with_usage_preflight:714` +
  `_usage_preflight_rank:734` reorder by reported `file_upload`/`image_gen`/
  `deep_research`; `not_reported` treated as unknown, not blocked.
- **Model resolution:** `auto`, `gpt-5-5*`, thinking/pro variants,
  `gpt-image-1`, `chatgpt-deep-research`, `@optimized`/`@opencode` suffixes.
- **Provider invocation:** `ChatGPTProvider` loads capture
  (`CapturedRequest.from_file`), builds `ChatGPTAuthConfig.from_captured_request`,
  replays via `transport.py` (`curl_cffi`/websockets).
- **Streaming:** SSE `chat.completion.chunk` then `data: [DONE]`.
- **Result normalization:** OpenAI-shaped `chat.completion` /
  `images.data[]` / `chatgpt.vision`; errors normalized with `code`s
  (`chatgpt_model_limit`, `chatgpt_rate_limited`,
  `chatgpt_unsupported_model`, `chatgpt_auth_or_browser_challenge`).
- **Artifact storage:** images → `outputs/chatgpt-images/`, research →
  `outputs/chatgpt-research/`; registered in `artifacts` table; download via
  `/v1/chatgpt/files/{file_id}/{filename}`.
- **Error handling:** OpenAI-shaped error objects; `_public_status_error`
  (~4370) sanitizes exceptions.
- **Cancellation:** in-memory `_ChatGPTOperation` (`openai_compat.py:175-188`);
  best-effort; Deep Research needs `conversation_id` + `message_id` + widget
  `session_id` before MCP `stop`.
- **Restart behavior:** operation records **lost**; artifact downloads
  **restorable** from admin DB when the file exists.
- **Test coverage:** `tests/test_openai_compat.py`, `test_chatgpt_transport.py`,
  `test_admin_store.py`, `test_crypto.py`, `test_request_capture.py`,
  `test_chatgpt_auth.py`. 188 pass + 1 Windows `0o600` platform failure.

## 3. Existing persistence (`BridgeAdminStore`, `admin_store.py`)

- **Tables:** `artifacts`, `account_captures`, `settings`
  (`_migrate():27-64`, `CREATE TABLE IF NOT EXISTS`, **idempotent**, no
  migration framework).
- **`artifacts` columns:** `file_id` (PK), `kind`, `filename`, `path`,
  `download_url`, `content_type`, `bytes`, `account`, `prompt`,
  `metadata_json`, `created_at`. Index `artifacts_created_idx` on
  `created_at DESC`.
- **`account_captures` columns:** `account` (PK), `capture_path`,
  `plan_type`, `email_masked`, `capabilities_json`, `checks_json`,
  `updated_at`.
- **`settings` columns:** `key` (PK), `value_json`, `updated_at`.
- **Behavior:** `record_artifact` (`INSERT OR REPLACE`, preserves
  `created_at`), `list_artifacts` (prunes stale rows whose file is missing),
  `delete_artifact(s)`, `record_account_capture`, `get_setting`/`set_setting`.
- **Transaction boundaries:** each `_connect()` is a new connection; `with`
  block commits/rolls back. No connection pooling.
- **Thread-safety:** `sqlite3` default `check_same_thread` — each call opens
  its own connection, so cross-thread use is safe but not pooled.
- **In-memory operation state:** `_CHATGPT_OPERATIONS` dict
  (`openai_compat.py:190`) + `_CHATGPT_OPERATIONS_LOCK`; pruned by
  `_prune_chatgpt_operations` (~492, 3600s). **Lost on restart.**
- **Data lost on restart:** all running operation records; in-flight
  cancellation state.
- **Cleanup:** stale artifact rows pruned on list/count; operation records
  pruned by age.
- **Artifact restoration:** yes — `file_id` → admin DB → file path.

## 4. Existing storage

- Generated images: `outputs/chatgpt-images/`.
- Edited images: same `chatgpt-images/` store.
- Research reports: `outputs/chatgpt-research/` (markdown).
- SQLite: `outputs/chatgpt-admin.sqlite` (Docker `/data/outputs/...`).
- Uploaded input files: **not persisted** — source images are parsed into
  bytes (`image_inputs.py`) and uploaded to ChatGPT transiently; no local
  copy kept.
- `file_id` → file mapping: `artifacts.path` + `artifacts.filename`.
- Filename sanitization: artifact filenames are derived (e.g. `icon.png`,
  `llm-agi.md`); `file_id` is opaque.
- Download: `GET/HEAD /v1/chatgpt/files/{file_id}/{filename}`.
- Restorable after restart: yes (if file exists).
- Path traversal: `file_id` resolved from registry/DB, not from the URL path
  directly; filename is the stored artifact filename. (No explicit
  `..`-sanitize function found — relies on DB lookup, which is the control.)
- Deletion: `delete_artifact` (metadata) / `delete_artifacts` (metadata
  only); file deletion is a separate operator action.
- Pruning: stale rows removed when their file is missing.
- Backup: none automated.

## 5. Existing security model

- **Shared API key:** `CHATGPT_API_KEY` (default `local-dev-key`).
- **Unset key ⇒ open** (`authorize` returns True, `http_utils.py:13`).
- **Default example:** `local-dev-key` (publicly known).
- **CORS:** `*` (permissive).
- **Admin/operator endpoints:** protected by the **same** shared key; no
  separate operator role. An external agent with the key **can** reach
  `/v1/chatgpt/admin/*` including capture management.
- **Artifact downloads:** same shared key gate; generated content exposed to
  anyone with bridge access.
- **Capture encryption:** Fernet `enc:v1:` (`crypto.py`); key from runtime
  passphrase > `CHATGPT_SECRETS_PASSPHRASE` > auto `.master.key` (0600 on
  POSIX, not on Windows).
- **Secret-file handling:** `secrets/`, `.env`, `*.har`, captures in
  `.gitignore` + `.dockerignore`.
- **LAN exposure risk:** weak key + `0.0.0.0` bind + CORS `*` = unsafe.
- **Public exposure risk:** critical — no TLS, no RBAC, single key.
- **No RBAC, no tenant isolation.**
- **Agent/operator boundary:** **shared** — same key covers both.

## 6. Existing frontend architecture (`apps/bridge-console`)

- **Structure:** Svelte 5 SPA, Vite 8, Tailwind v4, TypeScript, `lucide-svelte`.
- **Routing:** hash-based (`location.hash` + `hashchange` listener in
  `App.svelte` `onMount` ~859-864); `page` state drives `currentPage`.
- **Pages** (`pages` constant ~658-667): `overview`, `accounts`,
  `test-lab`, `limits`, `api-docs`, `storage`, `opencode`, `settings`.
- **API client:** `apiFetch` in `App.svelte` (~899-918); `baseUrl` +
  `apiKey` in `localStorage` (~688-689, 856-858); native `fetch` with
  `Authorization: Bearer <key>`.
- **State management:** Svelte 5 runes (`$state`, `$derived`); manual
  `refreshAll` (~933) + per-page `load*` functions; **controlled polling,
  no auto-SSE**.
- **Shared components** (`src/lib/`): `Badge.svelte`, `CodeBlock.svelte`,
  `Input.svelte`, `Textarea.svelte`, `PanelTitle.svelte`, `CaptureResult.svelte`,
  `ResponseFieldGuide.svelte`, `MetricGrid.svelte`, `ImageResult.svelte`.
- **Form/table/modal patterns:** forms via `Input`/`Textarea`; tables
  hand-built; modals/drawers minimal.
- **Artifact display:** `ImageResult.svelte` + storage page previews.
- **Account/settings views:** `accounts`, `limits`, `settings` pages.
- **Build/test:** `bun run check` (svelte-check), `bun run build` (Vite).
- **Console can host the Agent Job UI:** yes — hash routing + runes +
  `apiFetch` + existing Badge/Table/MetricGrid patterns are directly
  reusable. **No reason to create a third frontend.**

## 7. Reusable components

- `AIProvider`/`ProviderRegistry` — provider abstraction.
- `AccountRouter` + `BoundedSemaphore` limiters — routing + throttling.
- `BridgeAdminStore` — SQLite metadata (extend `_migrate`).
- Artifact download path (`/v1/chatgpt/files/{file_id}/{filename}`) —
  reuse for job artifacts.
- `image_inputs.py` — multimodal input parsing (path/URL/data-URL/base64).
- `prompts.py` — tool-bridge + Deep Research prompt policy.
- Redaction utilities — `redacted_headers()`, `to_redacted_dict()`,
  `_public_status_error()`.
- `crypto.py` — at-rest encryption for any stored sensitive input.
- Console `apiFetch`, `Badge`, `CodeBlock`, `MetricGrid`, `ImageResult`,
  `PanelTitle`.

## 8. Gaps

- No durable job/queue/result store.
- No idempotency.
- No restart recovery for in-flight work.
- No agent-facing async API.
- No job listing/filtering/polling/SSE contract.
- No per-client auth / capability scopes.
- No request-size/MIME/upload limits enforced at the API layer for a
  persistent input store.
- No callback/webhook delivery.
- No audit log.
- No automated backup/restore.

## 9. Risks (verified, current)

- Single shared key + CORS `*` + no RBAC → unsafe beyond a trusted LAN.
- In-memory operations lost on restart → unrecoverable in-flight jobs.
- `openai_compat.py` is 5,580 lines → high blast radius for edits.
- Captures expire (~10 days) → jobs fail with auth errors, not retryable
  indefinitely.
- Token usage is zero placeholders → no billing/quota logic possible on
  returned counts.

## 10. Code/document conflicts

- `docs/ARCHITECTURE.md` "API Module Map" lists **future** splits
  (`routing.py`, `artifacts.py`, `admin_routes.py`, `tool_bridge.py`) as
  planned, **not done** (`CLAUDE.md` §17 confirms). Do not assume they exist.
- Dockerfile `ENV` hardcodes `CHATGPT_ACCOUNT=free`/`CHATGPT_ACCOUNTS=free`;
  Compose overrides to blank — bare-`docker run` caveat only.
- `.env.example` legacy single-token vars (`CHATGPT_ACCESS_TOKEN`, etc.) are
  dev/diagnostic; the runtime capture flow is `secrets/accounts/<alias>/...`.
- README "189 passed" snapshot was recorded on Unix; on Windows it is 188 + 1
  platform failure (`CLAUDE.md` §17).
