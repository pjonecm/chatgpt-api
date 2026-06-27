# CLAUDE.md

Operational guide for Claude Code sessions working in this repository.
Grounded in the repository as of 2026-06-27. When code and this file disagree,
trust the code.

## 1. Project Overview

`chatgpt-api` is a **local OpenAI-shaped API bridge** backed by ChatGPT Web
browser sessions. It is a provider-first framework: a user runs a local HTTP
server whose `/v1` routes look close enough to common OpenAI client conventions
for development, while a captured ChatGPT Web browser request is the first
provider target.

- **Primary users:** developers testing OpenAI-shaped client flows locally
  without paid OpenAI API spend; operators running a private LAN bridge;
  app authors using the bridge as a backend.
- **Current phase:** working reference prototype (not a hosted product). Core
  bridge, account capture, routing, chat/streaming, image generation/edit,
  vision/OCR, Deep Research export, artifact downloads, Docker, CLI, and
  console are implemented and tested. Production hardening (multi-tenant auth,
  vaulting, durable queues, audit) is explicitly out of scope — see README
  "Scope Tiers".
- **Architecture summary:** Python stdlib `http.server` facade
  (`chatgpt_api/api/openai_compat.py`) → provider registry → ChatGPT Web
  transport (replays captured browser requests over `curl_cffi`/websockets).
  SQLite for admin metadata. Two Svelte frontend apps and an opencode
  integration live at the edge and consume the `/v1` API.

The project is **not** the official OpenAI API and must not be described as a
drop-in clone. Use the wording "OpenAI-shaped" / "Chat Completions-style".

## 2. Repository Map

```text
chatgpt_api/
  core/              Provider-neutral types, registry, errors (no provider logic)
  providers/chatgpt/ ChatGPT Web provider: capture parse, auth, proof, transport, models, crypto
  api/               Local HTTP facade + admin/runtime surface
    openai_compat.py Main facade (route orchestration; ~5.6k lines, intentionally large)
    config.py        OpenAICompatConfig (immutable server config)
    http_utils.py    Bearer auth, CORS, JSON body parsing, response helpers
    prompts.py       Tool-bridge + Deep Research prompt policy constants
    image_inputs.py  Image input parsing (path/URL/data-URL/base64/multimodal)
    admin_store.py   SQLite metadata: artifacts, account_captures, settings
apps/
  bridge-console/    Operator console (Svelte 5 SPA, static build served by nginx)
  character-game/    "Arcadia Sessions" SvelteKit full-stack reference app
integrations/opencode/  opencode consumer config + setup wizard (optional, edge)
docs/                Source-of-truth public/operator docs
references/legacy/   Legacy provider experiment — NOT runtime, not imported by package
tests/               Python unit tests (pytest)
secrets/accounts/   Local account captures (gitignored, never commit)
outputs/             Generated images, research reports, SQLite metadata (gitignored)
```

## 3. Technology Stack

Verified from `pyproject.toml`, `Dockerfile`, and app manifests.

- **Language/runtime:** Python ≥ 3.11 (`requires-python = ">=3.11"`); Docker
  uses Python 3.12-slim.
- **Backend HTTP:** Python stdlib `http.server.ThreadingHTTPServer` + a
  `BaseHTTPRequestHandler` subclass. **No web framework.** SSE streaming is
  hand-rolled.
- **Python deps:** `cryptography` (capture encryption at rest), `curl_cffi`
  (browser-impersonated HTTP for ChatGPT Web), `httpx`, `websocket-client`.
- **Dev deps:** `pytest>=8` only.
- **Database:** stdlib `sqlite3` for the bridge admin store; `better-sqlite3`
  inside the character-game app (separate DB).
- **Frontend:** Svelte 5 + Vite 8 + Tailwind v4 + TypeScript, managed with
  `bun`. `bridge-console` builds to static assets served by nginx;
  `character-game` is SvelteKit (`@sveltejs/adapter-node`) with `zod`.
- **Container:** Docker (multi-stage), Docker Compose with three services.
- **Package manager (Python):** pip / setuptools; console script
  `chatgpt-api = chatgpt_api.cli:main`. Also runnable as
  `python -m chatgpt_api`.

## 4. Source-of-Truth Documents

No `PROJECT.md`, `ROADMAP.md`, `CURRENT_STATE.md`, `ACTIVE_TASKS.md`, or
`IMPLEMENT_LOG.md` exist in this repo — do not invent them. Governance lives in
`docs/`:

| Document | Governs |
| --- | --- |
| `docs/ARCHITECTURE.md` | Provider-first boundaries, facade shape, open-source rules, planned module splits |
| `docs/OPENAI_COMPATIBILITY.md` | Public `/v1` API contract: routes, response shapes, model aliases, known gaps |
| `docs/ACCOUNT_CAPTURE.md` | How to capture, inspect, save, and refresh ChatGPT browser requests |
| `docs/DOCKER.md` | Compose stack, host volumes, environment variables |
| `docs/CLI.md` | Operator CLI command reference |
| `docs/PROJECT_ANALYSIS.md` | Maintainer map of surfaces, ownership, refactor status, security model |
| `docs/OPENCODE_AGENT_ROADMAP.md` | opencode integration contract and limits |
| `README.md` | Public overview, quick start, validation snapshot |

**Precedence for conflicts (highest → lowest):**
1. Current executable code and configuration (`chatgpt_api/`, `Dockerfile`,
   `docker-compose.yml`, app manifests).
2. SQLite schema in `chatgpt_api/api/admin_store.py` (`_migrate`).
3. Automated tests in `tests/`.
4. `docs/OPENAI_COMPATIBILITY.md` and `docs/ARCHITECTURE.md` (contracts).
5. `README.md` validation snapshot and `docs/PROJECT_ANALYSIS.md`.
6. Roadmap / "remaining technical debt" sections (intent, not implementation).

Never treat roadmap or "should be split" statements as completed work.

## 5. Required Reading Before Changes

- **Architecture / module boundaries:** `docs/ARCHITECTURE.md` and the "API
  Module Map" + "Remaining Technical Debt" sections of
  `docs/PROJECT_ANALYSIS.md`.
- **API route or response shape:** `docs/OPENAI_COMPATIBILITY.md` and the
  route handlers in `chatgpt_api/api/openai_compat.py`.
- **Database / admin store:** `chatgpt_api/api/admin_store.py` (schema +
  migration are inline; no separate migration files).
- **Auth / secrets / captures:** `docs/ACCOUNT_CAPTURE.md`,
  `chatgpt_api/api/http_utils.py` (`authorize`), and
  `chatgpt_api/providers/chatgpt/crypto.py`.
- **Account routing / concurrency:** `AccountRouter` and throttle logic in
  `chatgpt_api/api/openai_compat.py`; `docs/PROJECT_ANALYSIS.md`
  "Account Routing And Capacity".
- **Tool bridge / prompts:** `chatgpt_api/api/prompts.py` and the
  `_build_chat_prompt` / `_parse_tool_calls` path in `openai_compat.py`.
- **Deployment / env:** `docs/DOCKER.md`, `.env.example`, `Dockerfile`,
  `docker-compose.yml`.

## 6. Development Commands

Run Python commands from the **repo root**. Run frontend commands from each
app directory.

```sh
# Python (from repo root)
python -m pip install -e '.[dev]'     # install editable + pytest
python -m compileall chatgpt_api      # syntax/byte-compile check (no deps executed)
python -m pytest -q                   # full Python suite (189 tests; see §17 re: Windows)

# Start the bridge API (both forms are equivalent; serve is the alias)
python -m chatgpt_api serve --host 127.0.0.1 --port 8000
python -m chatgpt_api server start --api-key local-dev-key
python -m chatgpt_api doctor          # setup + API health check
python -m chatgpt_api menu            # interactive TTY control center

# bridge-console (from apps/bridge-console)
bun install
bun run check        # svelte-check diagnostics
bun run build        # production build to dist/
bun run dev          # Vite dev server on 127.0.0.1:5174

# character-game (from apps/character-game)
bun install
bun run check        # svelte-check
bun test             # vitest unit tests (run with -- --run)
bun run build        # SvelteKit node build
bun run dev          # dev server (~5173); CHATGAME_AI_MODE=mock for UI-only work

# Docker (from repo root)
docker compose up --build             # api :8000, console :8080, game :3000
```

The console script `chatgpt-api` is available after install. The Dockerfile
`CMD` is `chatgpt-api server start`.

## 7. Architecture and Data Flow

Principal runtime path for a chat completion:

1. Client sends OpenAI-shaped `POST /v1/chat/completions` with Bearer key.
2. `OpenAICompatHandler` (in `openai_compat.py`) parses the body; `authorize()`
   checks the Bearer token against `CHATGPT_API_KEY` (no key = open).
3. `AccountRouter` selects a ChatGPT account alias using the configured
   strategy (`auto`/`sticky`/`failover`/`round-robin`/`weighted`/
   `quota-aware`/`random`); a `BoundedSemaphore` enforces per-account,
   per-feature (chat/upload/image/research) concurrency.
4. The handler resolves the model alias (`auto`, `gpt-5-5*`,
   `chatgpt-deep-research`, `@optimized`/`@opencode` suffixes) and, if
   `tools` are present, injects the tool-bridge prompt from `prompts.py`.
5. `ChatGPTProvider` loads the encrypted capture for the chosen account
   (`secrets/accounts/<alias>/chatgpt-request.txt`), decrypts it via
   `crypto.py`, refreshes web tokens as needed, and replays a browser-shaped
   request to `https://chatgpt.com/backend-api/f/conversation` through
   `curl_cffi` / websockets (`providers/chatgpt/transport.py`).
6. The provider streams events back; the facade normalizes them into OpenAI
   `chat.completion` or SSE `chat.completion.chunk` objects, or parses
   `tool_calls` JSON for agent clients.
7. Image/research routes save artifacts under `outputs/` and register them in
   the SQLite admin store; download URLs are served via
   `/v1/chatgpt/files/{file_id}/{filename}`.

The server **never executes tools** — it only translates between OpenAI-shaped
`tools` and ChatGPT Web text. Tool execution belongs to the client (e.g.
opencode) or app runtime (e.g. character-game).

## 8. Roles and Authorization

This project has **no application role or permission model**. Be explicit about
this; do not imply RBAC that does not exist.

- The only authentication is an **optional shared Bearer token**
  (`CHATGPT_API_KEY`, default example `local-dev-key`), enforced by
  `authorize()` in `http_utils.py`. When the key is unset, all routes are open.
  When set, every protected route requires `Authorization: Bearer <key>`.
- There are no user accounts, no admin role, no route guards per role, and no
  frontend role switching. "Admin" routes (`/v1/chatgpt/admin/*`) are operator
  endpoints protected by the same shared key — not a privileged user role.
- The `free` / `go` / `plus` / `pro` labels are **ChatGPT account plan tiers**
  used to size local concurrency limits, not authorization roles. Account
  names (`main-free`, `image-pro`, …) are local operator-chosen aliases, not
  plan selectors.
- The character-game app has its own `CHATGAME_AI_MODE=mock` flag for UI-only
  development; that is a **development-only mock** and is explicitly not the
  product path (see `apps/character-game/README.md`).

Do not claim security guarantees not enforced in code.

## 9. Implementation Workflow

1. Read the relevant source-of-truth doc(s) from §5.
2. Inspect the current implementation in `chatgpt_api/` (or the target app).
3. Identify the active task and its acceptance criteria.
4. Check architecture, API, schema, and auth/secrets implications.
5. Implement the smallest coherent change; reuse existing patterns.
6. Add or update tests under `tests/` (Python) or the app's spec files.
7. Run the relevant validation from §14.
8. Update affected docs (`docs/`, app READMEs) and, if the public behavior
   changed, the README validation snapshot date/claim.
9. Report changed files, validation results, risks, and remaining work (§18).

## 10. Coding and Change Rules

- No speculative architecture changes. Do not pre-implement the module splits
  listed as "Remaining Technical Debt" unless that is the task.
- No new dependency without justification; `pyproject.toml` is intentionally
  tiny.
- No API contract change without reviewing `docs/OPENAI_COMPATIBILITY.md` and
  the route handler together.
- No database/schema change without updating the inline `_migrate()` in
  `admin_store.py` (there is no separate migration framework).
- No bypassing backend authorization through UI logic — the shared Bearer key
  is the only enforcement; do not add client-side "admin" gating as if it were
  security.
- No treating mock or development behavior (`CHATGAME_AI_MODE=mock`, unset API
  key, `local-dev-key`) as production behavior.
- No unrelated refactoring. `openai_compat.py` and `cli.py` are intentionally
  large; split only when a task creates a clear ownership boundary and tests
  stay green.
- Preserve backward compatibility for public route shapes and CLI command
  names unless the task explicitly changes them.
- Reuse existing project patterns (stdlib HTTP helpers, dataclasses with
  `slots=True`, redacted summaries) before introducing abstractions.
- Avoid duplicating business rules across layers; provider quirks stay in
  `providers/chatgpt/`, API shapes stay in `api/`.

## 11. Database Rules

- The bridge admin DB is **SQLite via stdlib `sqlite3`**, default path
  `outputs/chatgpt-admin.sqlite` (Docker: `/data/outputs/chatgpt-admin.sqlite`).
- Schema is defined inline in `BridgeAdminStore._migrate()` using
  `CREATE TABLE IF NOT EXISTS` — there is **no migration framework** and no
  migration files. Schema changes go there and must remain idempotent.
- Tables: `artifacts` (generated files + download URLs), `account_captures`
  (alias → capture path, plan, capabilities, checks), `settings` (persisted
  operator settings as JSON).
- The store prunes stale artifact rows whose files no longer exist on disk.
- Operation records (cancel/inspect) are **in-memory runtime state**, not
  persisted — they do not survive process/container restart. Artifact
  downloads are restorable from the admin DB when the file still exists.
- The character-game app owns its own separate SQLite DB (`better-sqlite3`,
  default `.data/arcadia.sqlite`); it is not part of the bridge admin store.
- No seed data; no ORM.

## 12. API Rules

- Public OpenAI-shaped routes (verified in `openai_compat.py` and
  `docs/OPENAI_COMPATIBILITY.md`):
  `GET /health`, `GET /v1/models`, `POST /v1/chat/completions`,
  `POST /v1/images/generations`, `POST /v1/images/edits`,
  `POST /v1/chatgpt/vision`, `GET /v1/chatgpt/usage`,
  `GET|HEAD /v1/chatgpt/files/{file_id}/{filename}`,
  `GET /v1/chatgpt/operations/{operation_id}`,
  `POST /v1/chatgpt/operations/{operation_id}/cancel`.
- Operator/admin routes live under `/v1/chatgpt/admin/*` (status, accounts,
  captures/inspect|save, accounts/check|delete, settings/save|reset,
  artifacts, artifacts/delete, opencode/inject|eject, test/chat|image).
  These are local operator endpoints, **not** stable public client endpoints.
- `GET /v1/models` is the source of truth for the current server route; it
  merges capabilities inferred from configured account captures.
- Known contract gaps (documented, do not "fix" silently): token usage is
  returned as **zero placeholders**; `n` for image generation is fixed to 1;
  `/v1/images/edits` accepts JSON image references, not official multipart;
  tool calling uses a prompt bridge, not native tool-call API.
- Errors are OpenAI-shaped error objects with normalized `code` for ChatGPT
  cases (`chatgpt_model_limit`, `chatgpt_rate_limited`,
  `chatgpt_unsupported_model`, `chatgpt_auth_or_browser_challenge`).
- Deep Research (`model: chatgpt-deep-research`) requires **normal
  (non-temporary) chat mode** and saves a markdown report artifact; the
  response must not re-summarize the report.

## 13. Frontend Rules

Two independent apps; neither is part of the Python package.

- **`apps/bridge-console`** — Svelte 5 SPA, stateless control plane. Calls the
  bridge `/v1/chatgpt/admin/*` and `/v1` routes; does **not** own capture
  persistence (the API does). Built to static assets served by nginx in
  Docker. Dev: `bun run dev` (127.0.0.1:5174). Check before commit:
  `bun run check`.
- **`apps/character-game`** — SvelteKit full-stack reference app. Its server
  routes (`src/routes/api/*`) call the bridge's `/v1/chat/completions` and
  `/v1/images/generations`; it owns its own SQLite state, streaming turn UX,
  image jobs, and cancellation. Browser clients never receive captures, API
  keys, or account data. Dev: `bun run dev` (~5173).
- **API access pattern:** server-side fetch to the bridge; the browser only
  talks to the app's own `/api/*` routes. In Docker, `CHATGAME_OPENAI_BASE_URL`
  is the internal service URL and `CHATGAME_PUBLIC_OPENAI_BASE_URL` is the
  browser-facing URL.
- **State management:** character-game persists to its own SQLite via
  `src/lib/server/store.ts`; the console is stateless and renders API state.
- **Auth integration:** apps pass through the bridge Bearer key
  (`CHATGPT_OPENAI_API_KEY` / `CHATGAME_OPENAI_API_KEY`); they do not perform
  their own user auth.
- **Mock mode:** `CHATGAME_AI_MODE=mock` lets character-game UI be developed
  without a running bridge. Mark clearly as dev-only; never treat as the
  product path.
- **Styling/conventions:** Tailwind v4; `lucide-svelte` icons; `prettier` +
  `svelte-check` are the gates. Character-game also runs `eslint` and `vitest`.

## 14. Testing and Validation

Run the checks matching the change type. All Python commands run from repo
root; frontend commands from the app directory.

| Change type | Commands |
| --- | --- |
| Backend-only | `python -m compileall chatgpt_api`, `python -m pytest -q` |
| API route / response shape | `python -m pytest -q` (esp. `tests/test_openai_compat.py`), then smoke `python -m chatgpt_api api chat --message "bridge ok"` against a running server |
| Schema / admin store | `python -m pytest tests/test_admin_store.py -q` |
| Auth / secrets / capture | `python -m pytest tests/test_crypto.py tests/test_request_capture.py tests/test_chatgpt_auth.py -q` |
| Routing / transport | `python -m pytest tests/test_chatgpt_transport.py tests/test_openai_compat.py -q` |
| bridge-console UI | `bun run --cwd apps/bridge-console check && bun run --cwd apps/bridge-console build` |
| character-game | `bun run --cwd apps/character-game check && bun run --cwd apps/character-game test && bun run --cwd apps/character-game build` |
| Docker / deployment | `docker compose up --build`; then `curl -H 'Authorization: Bearer local-dev-key' http://127.0.0.1:8000/health` and `curl http://127.0.0.1:3000/api/status` |
| Docs-only | no automated gate; re-read affected doc and grep for stale aliases |

Live chat/image/OCR/research validation requires a real captured ChatGPT
account under `secrets/accounts/`; report this limitation if no capture is
available.

## 15. Documentation Write-Back

Only documents that exist in this repo are in scope. After implementation,
update:

- `docs/OPENAI_COMPATIBILITY.md` — for any public `/v1` route, response shape,
  model alias, or known-gap change.
- `docs/ARCHITECTURE.md` — for module boundary or facade-shape changes.
- `docs/ACCOUNT_CAPTURE.md` — for capture format, validation, or file-layout
  changes.
- `docs/DOCKER.md` and `.env.example` — for environment variable or compose
  changes (keep them in sync).
- `docs/CLI.md` — for new/changed CLI commands.
- `docs/PROJECT_ANALYSIS.md` — for surface-ownership or refactor-status
  changes.
- App `README.md` files — for app-facing API or env changes.
- `README.md` "Latest Validation Snapshot" — re-run the listed checks and
  update the date/results when public behavior changes. Keep snapshot claims
  truthful (see §17).

There is no `CURRENT_STATE.md` / `ACTIVE_TASKS.md` / `IMPLEMENT_LOG.md`. Do
not create backlog files unless the task explicitly asks. Historical/legacy
notes (e.g. `references/legacy/`) must remain clearly marked as legacy; do not
inject stale instructions into current source-of-truth sections.

## 16. Security and Safety Constraints

Verified constraints; do not weaken them.

- **Never commit** `secrets/`, `.env`, `outputs/`, copied headers, cookies,
  bearer tokens, sentinel/proof/conduit tokens, or raw captures. `.gitignore`
  and `.dockerignore` enforce this; keep them covering new secret paths.
- **Never log** raw `Authorization` headers, cookies, sentinel tokens, or
  capture contents. Show redacted summaries only (detect plan/account
  metadata + missing-field diagnostics).
- **Captures are credentials.** They contain live ChatGPT browser sessions.
  Captures are encrypted at rest (`providers/chatgpt/crypto.py`,
  `cryptography`) under `secrets/accounts/<alias>/chatgpt-request.txt`; a
  passphrase (`--secrets-passphrase-prompt`) or auto-generated key file
  (`.master.key`) decrypts them. Rotate with `chatgpt-api secrets rotate`.
- **Auth:** single optional Bearer token (`CHATGPT_API_KEY`). Default
  `local-dev-key` is a dev example, not a secret. Binding defaults to
  `127.0.0.1`; only bind `0.0.0.0` intentionally for LAN/Docker.
- **CORS:** `Access-Control-Allow-Origin: *` is sent on responses. This is
  permissive — appropriate for a local bridge, not for a public deployment.
- **File access:** artifact downloads (`/v1/chatgpt/files/{id}/{filename}`)
  serve from `outputs/`; `file_id` resolves from the in-memory registry then
  the admin DB. Do not expose arbitrary filesystem paths.
- **SQL:** uses parameterized queries in `admin_store.py`; keep it that way.
- **No external storage** — all artifacts are local files + SQLite.
- **Development-only surfaces:** `CHATGAME_AI_MODE=mock`, unset API key, and
  the interactive `menu`/`doctor` commands are not production hardening.

## 17. Known Limitations and Active Risks

- **`openai_compat.py` is ~5,580 lines** and `cli.py` is ~3,600 lines. Both
  are intentionally monolithic for now; planned splits (routing, operations,
  artifacts, admin_routes, tool_bridge, model_catalog) are documented as
  future work in `docs/PROJECT_ANALYSIS.md`, **not done**. Do not assume they
  exist.
- **Single shared API key, no multi-tenant auth.** Anyone with the key has
  full operator access including account capture management. Not safe as-is
  for public hosting.
- **CORS `*`** — permissive; local-only by design.
- **Platform note (Windows):** `tests/test_crypto.py::
  test_load_secrets_key_creates_owner_only_key_file` asserts Unix `0o600` file
  permissions, which NTFS does not enforce. On Windows this test fails
  (`438 == 0o666` vs expected `384 == 0o600`); the other 188 tests pass. The
  README "189 passed" snapshot was recorded on a Unix-like system. This is a
  test/platform mismatch, not a code defect.
- **Captures expire** (~10 days, not guaranteed) and can be revoked by logging
  out of ChatGPT. The bridge cannot repair an expired capture locally.
- **Hidden ChatGPT rate limits** apply beyond the local concurrency throttles;
  preflight only reorders accounts by reported quota and treats `not_reported`
  as unknown, not blocked.
- **`references/legacy/OpenaiChat.py`** is a legacy experiment that imports
  modules (`zendriver`, `requests.curl_cffi`) not present in current deps. It
  is not imported by the package and must not be wired into runtime.
- **Token usage is zero placeholders**; do not build billing/quota logic on
  returned token counts.

## 18. Completion Report Format

When finishing a task, report:

- **Objective** — what was to be done.
- **Files changed** — every path.
- **Implementation summary** — what changed and why, concisely.
- **Commands run** — exact commands, from which directory.
- **Validation results** — pass/fail/not-run per command, with output for
  failures.
- **Unresolved issues** — including platform-specific skips and any check that
  could not run (e.g. no captured account available).
- **Documentation updated** — which `docs/` / README sections changed.
- **Recommended next action** — one concrete follow-up.
