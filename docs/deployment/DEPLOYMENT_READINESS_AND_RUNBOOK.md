# Deployment Readiness Assessment and Runbook

> Status: **audit + runbook only.** No deployment, no production changes, no
> data mutation was performed to produce this document.
>
> Verified against repository evidence on **2026-06-27**. When code and this
> document disagree, trust the code (see `CLAUDE.md` §0).

This document is a **project-specific** assessment. It distinguishes:

- **Verified implementation** — confirmed by reading code/config and running
  non-destructive checks.
- **Documented but not implemented** — described in docs but absent from code.
- **Legacy / development-only** — present but explicitly not production.
- **Production-required but missing** — gaps that block a real deployment.

It is written for a single operator taking the existing Docker Compose stack
to a **private LAN / single-host** deployment. Public multi-tenant hosting is
explicitly out of scope for this codebase (see `README.md` "Scope Tiers" and
`CLAUDE.md` §1, §8, §17) and is **not** covered by the runbook as a supported
target.

---

## 1. Executive Summary

`chatgpt-api` is a **local OpenAI-shaped API bridge** backed by captured
ChatGPT Web browser sessions. The repository ships a working Docker Compose
stack of three services (Bridge API, operator Console, Character Game), a
Python CLI, encrypted-at-rest account captures, SQLite admin metadata, and
artifact downloads.

**Readiness verdict: `READY WITH CONDITIONS`** for a **private single-host /
LAN** deployment.

The stack builds, the Compose file validates, the API Dockerfile includes a
healthcheck, the SQLite schema auto-migrates on first use (idempotent,
no separate migration step required), captures are encrypted at rest, and the
Python test suite passes except for the documented Windows
file-permission platform mismatch, which is not a code defect.

The conditions are **security and operational**, not build:

1. The only auth is a **single shared Bearer token** (`CHATGPT_API_KEY`,
   default `local-dev-key`). Anyone with the key has full operator access
   including account-capture management. This is a **deployment blocker for
   any non-isolated network** — the key must be rotated to a strong secret and
   the surface must be kept off the public internet.
2. **CORS is `Access-Control-Allow-Origin: *`** (verified in
   `http_utils.py:34` and `openai_compat.py:2273`). Intentional for a local
   bridge; unsafe for a public deployment.
3. **`CHATGPT_PUBLIC_BASE_URL` defaults to `127.0.0.1:8000/v1`** in both the
   Dockerfile and Compose. For LAN clients this must be overridden to the
   reachable host URL or artifact download links point back at the client.
4. **Live ChatGPT calls require at least one captured account** under
   `secrets/accounts/<alias>/chatgpt-request.txt`. Without a capture, the stack
   boots but chat/image/research return auth errors. Captures are credentials,
   expire (~10 days, not guaranteed), and cannot be repaired locally.
5. **No CI/CD pipeline** (`.github/` absent), **no deployment scripts**
   (`scripts/` absent), and **no automated backup/rollback tooling** exists in
   the repo. Backup and rollback are operator-manual.

This codebase is **not** ready for public multi-tenant hosting and the project
explicitly does not claim to be (see `README.md` "Scope Tiers" → "Production
TODO"). Adding RBAC, tenant isolation, secret vaulting, durable queues,
audit, and abuse controls is documented future work, **not** present code.

---

## 2. Repository Evidence Reviewed

| Source | Path | Read |
| --- | --- | --- |
| Operational guide | `CLAUDE.md` | yes |
| Public overview | `README.md` | yes |
| Python manifest | `pyproject.toml` | yes |
| API image | `Dockerfile` | yes |
| Compose stack | `docker-compose.yml` | yes |
| Env template | `.env.example` | yes |
| Game env template | `apps/character-game/.env.example` | yes |
| Ignore rules | `.gitignore`, `.dockerignore` | yes |
| Docker guide | `docs/DOCKER.md` | yes |
| HTTP auth/CORS | `chatgpt_api/api/http_utils.py` | yes |
| Admin store / schema | `chatgpt_api/api/admin_store.py` | yes |
| Capture crypto | `chatgpt_api/providers/chatgpt/crypto.py` | grep |
| Console Dockerfile | `apps/bridge-console/Dockerfile` | yes |
| Console nginx | `apps/bridge-console/nginx.conf` | yes |
| Game Dockerfile | `apps/character-game/Dockerfile` | yes |
| App manifests | `apps/bridge-console/package.json`, `apps/character-game/package.json` | yes |
| Game server routes | `apps/character-game/src/routes/api/*` | listing |
| Source-of-truth docs | `docs/*.md` | index + DOCKER |

**Confirmed absent** (per `CLAUDE.md` §4, verified by `ls`): no
`PROJECT.md`, `ROADMAP.md`, `CURRENT_STATE.md`, `ACTIVE_TASKS.md`,
`IMPLEMENT_LOG.md`, no `.github/` CI, no `scripts/` directory, no migration
files, no separate `compose.yaml`/override files.

---

## 3. Verified Architecture

### Verified implementation

- **Backend:** Python ≥ 3.11 (`pyproject.toml`; Docker uses `python:3.12-slim`).
  Stdlib `http.server.ThreadingHTTPServer` + `BaseHTTPRequestHandler`. **No
  web framework.** SSE streaming hand-rolled. Entry: `chatgpt-api server start`
  (`CMD` in `Dockerfile`) = `chatgpt_api.cli:main`.
- **Provider:** ChatGPT Web via `curl_cffi` + `websocket-client`; replays
  captured browser requests to `https://chatgpt.com/backend-api/f/conversation`.
- **Auth:** single optional shared Bearer token enforced by `authorize()` in
  `http_utils.py:11`. No key ⇒ all routes open (`return True`). **No RBAC, no
  user accounts, no admin role** (`CLAUDE.md` §8 confirmed in code).
- **Database:** stdlib `sqlite3`, default `outputs/chatgpt-admin.sqlite`
  (Docker: `/data/outputs/chatgpt-admin.sqlite`). Schema defined inline in
  `BridgeAdminStore._migrate()` via `CREATE TABLE IF NOT EXISTS` —
  **idempotent, runs in the store constructor on first use**, so no explicit
  migration step is required at deploy time. Tables: `artifacts`,
  `account_captures`, `settings`. Parameterized queries throughout.
- **Object/file storage:** local filesystem only. Images →
  `outputs/chatgpt-images/`, research → `outputs/chatgpt-research/`. Downloads
  served from `outputs/` via `/v1/chatgpt/files/{file_id}/{filename}`.
- **Captures:** credentials, encrypted at rest (`crypto.py`, `cryptography`)
  under `secrets/accounts/<alias>/chatgpt-request.txt`; auto key file
  `.master.key` or passphrase (`CHATGPT_SECRETS_PASSPHRASE` /
  `--secrets-passphrase-prompt`).
- **Frontend:** two independent apps.
  - `bridge-console`: Svelte 5 + Vite 8 + Tailwind v4; builds to static
    `dist/`, served by `nginx:alpine` on internal port `80` (host `8080`).
  - `character-game`: SvelteKit (`@sveltejs/adapter-node`); runs
    `node build/index.js` on port `3000`; owns its own `better-sqlite3` DB at
    `/data/chatgame.sqlite`. Browser → app `/api/*` → server-side fetch to
    bridge (never exposes captures/keys to the browser).
- **Health endpoints:** API `GET /health` (Dockerfile `HEALTHCHECK` calls it);
  console nginx `GET /health` returns `ok`; character-game has `/api/status`
  but **no Docker `HEALTHCHECK`**.
- **Ports:** API `8000`, console `8080`, game `3000`.
- **Persistence (Docker volumes):** `./secrets/accounts` →
  `/data/secrets/accounts`; `./outputs` → `/data/outputs`;
  `./outputs/character-game` → `/data` (game DB + image cache).
- **Env loading:** process environment only (read via `os.environ.get` in
  `cli.py` and the config layer). `.env` is consumed by `docker compose` /
  `docker run --env-file`, not by the Python app directly.

### Documented but not implemented

- Production hardening listed under `README.md` "Scope Tiers → Production
  TODO" (RBAC, tenant isolation, vaulting, durable queues, audit, abuse
  controls, observability, backup/restore automation) — **none present in
  code**; this is intent, not implementation (`CLAUDE.md` §17).

### Legacy / development-only (must not be wired into runtime)

- `references/legacy/OpenaiChat.py` — imports `zendriver` / `requests.curl_cffi`
  not in current deps; not imported by the package (`CLAUDE.md` §17).
- `CHATGAME_AI_MODE=mock` — UI-only dev mode; explicitly not the product path.
- `chatgpt-api doctor` / `menu` interactive TTY commands — operator
  convenience, not production hardening.
- `.env.example` single-token/HAR vars (`CHATGPT_ACCESS_TOKEN`,
  `CHATGPT_PROOF_TOKEN`, `CHATGPT_TURNSTILE_TOKEN`, `CHATGPT_COOKIES_JSON`,
  `CHATGPT_HEADERS_JSON`, `CHATGPT_HAR_PATH`, `CHATGPT_REQUEST_PATH`) —
  reference a legacy capture flow not used by the Compose runtime.

### Production-required but missing

- No multi-tenant auth / RBAC.
- No request audit log.
- No durable operation queue (operation records are in-memory, lost on
  restart — `admin_store.py` only persists artifacts/settings/captures).
- No automated backup or rollback tooling.
- No TLS termination in-repo (expected behind a reverse proxy / not provided).
- No CI pipeline to gate releases.

### Documentation/code conflicts found

- **None material.** The Dockerfile `ENV` sets `CHATGPT_ACCOUNT=free` /
  `CHATGPT_ACCOUNTS=free` (lines 23–24), but the Compose `environment:` block
  overrides both to blank (auto-discover). The bare-`docker run` path in
  `docs/DOCKER.md` relies on `--env-file .env` (where both are blank), so the
  hardcoded `free` only bites an operator who runs the image with no env and
  no `--env-file` and has no capture literally named `free`. Low-risk, but
  note it.
- The `character-game` Dockerfile hardcodes
  `CHATGAME_OPENAI_API_KEY=local-dev-key` (line 41); Compose overrides it with
  `${CHATGPT_API_KEY:-local-dev-key}`. Same caveat: bare `docker build`+`run`
  of the game image without Compose uses the weak default.

---

## 4. Verification Commands and Results

All commands run from repo root on Windows 11 / PowerShell unless noted.
Non-destructive only: no `docker compose up`, no image push, no DB reset.

| # | Command | WD | Validates | Result | Meaning |
| --- | --- | --- | --- | --- | --- |
| 1 | `python -m compileall chatgpt_api` | repo root | Python syntax/byte-compile | **PASS** (exit 0) | Package compiles cleanly. |
| 2 | `python -m pytest -q` | repo root | Python unit/integration suite | **PASS w/ 1 known-platform-fail** — 379 passed, 1 failed | Failure is `test_load_secrets_key_creates_owner_only_key_file` asserting Unix `0o600`; NTFS does not enforce it (`438 == 0o666` vs `384 == 0o600`). Documented in `CLAUDE.md` §17 and `README.md` snapshot. **Not a code defect.** |
| 3 | `docker compose -f docker-compose.yml config --quiet` | repo root | Compose syntax/resolution | **PASS** (exit 0) | Compose file valid; env interpolation resolves. |
| 4 | `bun run --cwd apps/bridge-console check` / `build` | app dir | Console Svelte diagnostics + build | **NOT AVAILABLE** — `bun` not installed on this machine | Validated in `README.md` "Latest Validation Snapshot" dated 2026-06-26 (`0 errors, 0 warnings`, build passed). Re-run on deploy host before release. |
| 5 | `bun run --cwd apps/character-game check` / `test` / `build` | app dir | Game Svelte diagnostics, vitest, build | **NOT AVAILABLE** — `bun` not installed | Validated in 2026-06-26 snapshot (`0 errors`, `6 tests passed`, build passed). Re-run on deploy host. |
| 6 | `docker compose up --build` + smoke curls | repo root | Full stack boot + live routes | **NOT RUN** — would start services (deployment action); also requires a captured account for real chat/image/research | Per task constraints, not executed. Run on the deploy host per runbook §9. |
| 7 | Live chat/image/OCR/research | — | End-to-end provider calls | **BLOCKED** — no account capture under `secrets/accounts/` (gitignored, expected) | Real ChatGPT calls cannot be verified without a captured account. |

**Corrective actions:**

- Install `bun` on the deploy host and re-run commands 4–5 before cutting a
  release; do not rely solely on the 2026-06-26 snapshot.
- Acquire at least one ChatGPT capture and add it via the console/CLI before
  expecting command 6's chat/image/research smoke to pass.

### Deployment-blocker scan (verified against code)

| Check | Finding | Evidence |
| --- | --- | --- |
| Hard-coded localhost URLs | `CHATGPT_PUBLIC_BASE_URL` defaults to `http://127.0.0.1:8000/v1` in `Dockerfile:30` and `docker-compose.yml:18` | LAN gotcha — override for non-local clients |
| Hard-coded weak API key | `local-dev-key` default in `cli.py:707`, `Dockerfile`, Compose `${CHATGPT_API_KEY:-local-dev-key}`, game Dockerfile `:41` | Must override in production |
| CORS | `Access-Control-Allow-Origin: *` | `http_utils.py:34`, `openai_compat.py:2273` — permissive, local-only by design |
| Auth enforcement | Single shared Bearer; no key ⇒ open | `http_utils.py:11` (`authorize`) |
| Debug/auth bypass | None found | `authorize` is the only gate; no dev backdoor |
| DB connection assumptions | Local SQLite file, auto-created | `admin_store.py:17-25` — no external DB required |
| Migration step | None required | `_migrate()` runs in constructor, idempotent `CREATE TABLE IF NOT EXISTS` |
| Local filesystem dependency | Yes — images/research/SQLite on disk | `outputs/` must be a mounted, writable volume |
| Port bindings | API binds `0.0.0.0:8000` in Docker | `Dockerfile:21`, Compose — intentional for Docker/LAN |
| Health/readiness | API has Docker `HEALTHCHECK` + `/health`; console nginx `/health`; game has `/api/status` but **no Docker HEALTHCHECK** | `Dockerfile:57`, `nginx.conf:12` |
| Secrets committed | None found | `secrets/`, `.env`, `*.har`, captures all in `.gitignore` + `.dockerignore` |
| Frontend/backend base URL mismatch | Game uses internal `http://chatgpt-api:8000/v1` (server-side) and `CHATGPT_PUBLIC_OPENAI_BASE_URL` (browser) derived from `CHATGPT_PUBLIC_BASE_URL` | `docker-compose.yml:55-56` — correct split |
| Volume persistence | `./secrets/accounts`, `./outputs`, `./outputs/character-game` mounted | `docker-compose.yml:31-33,65-66` — survive rebuilds |
| Backup/rollback tooling | **None in repo** | manual operator procedure (see §11) |
| CI/CD | **None** (`.github/` absent) | release gating is manual |

---

## 5. Deployment Readiness Verdict

### `READY WITH CONDITIONS` — private single-host / LAN deployment

**Main reason:** the stack is build-valid, config-valid, test-passing
(modulo a documented Windows-only test mismatch), auto-migrating, and ships
with healthchecks and encrypted captures; however its security model (single
shared Bearer key, CORS `*`, no RBAC, in-memory operation state, no
backup/rollback automation) limits it to a **trusted private network** with a
strong rotated key and an operator-managed backup/rollback discipline. Public
multi-tenant hosting is **NOT READY** and is out of scope for this codebase.

### Deployment Blockers (must fix before any deployment)

1. **Weak/default `CHATGPT_API_KEY`.** Default `local-dev-key` is publicly
   known. Set a strong random secret in `.env` before `docker compose up`.
2. **No capture = no working chat/image/research.** At least one valid
   ChatGPT capture must be mounted under `secrets/accounts/<alias>/`.
3. **Public exposure.** Do not expose ports `8000/8080/3000` to the public
   internet. Bind to the LAN/loopback or place behind a reverse proxy with
   TLS + an additional auth layer. (The repo provides no TLS.)

### Required Configuration (supplied outside the repo)

- `.env` with a strong `CHATGPT_API_KEY` and a host-reachable
  `CHATGPT_PUBLIC_BASE_URL`.
- One or more ChatGPT account captures (operator-supplied, never committed).
- A secrets strategy: prefer `--secrets-passphrase-prompt` (or
  `CHATGPT_SECRETS_PASSPHRASE` for headless Docker) over the auto key file for
  any deployment where the `secrets/` directory might be copied.
- Persistent host volumes for `./secrets/accounts` and `./outputs`.
- (If used) a reverse proxy with TLS in front of ports 8000/8080/3000.

### Recommended Hardening (not absolute blockers)

- Add a Docker `HEALTHCHECK` to the `character-game` service (currently none).
- Rotate captures weekly (they expire ~10 days; not guaranteed).
- Run `bun run check && bun run build` for both apps on the deploy host
  (re-validate beyond the 2026-06-26 snapshot).
- Back up `outputs/chatgpt-admin.sqlite` and `outputs/` artifacts on a
  schedule; the repo automates nothing.
- Lower `CHATGPT_*_CONCURRENCY` if you observe hidden ChatGPT burst limits.
- Restrict CORS to known origins if ever moving toward a trusted multi-client
  LAN (requires code change — currently hardcoded `*`).

### Verified Capabilities (reduce risk)

- Compose config validates (`config --quiet` exit 0).
- Python package compiles; on Windows, the full suite has the documented
  Unix `0o600` permission assertion mismatch while the remaining tests pass.
- SQLite schema is idempotent and auto-applied — no migration step to forget.
- Captures encrypted at rest; `.gitignore`/`.dockerignore` cover all secret
  paths.
- API Dockerfile runs as non-root `appuser` (uid 10001) with a `HEALTHCHECK`.
- Artifact download URLs survive restarts when volumes are mounted.
- Browser clients never receive captures, keys, or account data (game routes
  server-side through `/api/*`).

---

## 6. Deployment Blockers

(Restated for the runbook; see §5 for context.)

| # | Blocker | Fix |
| --- | --- | --- |
| B1 | `CHATGPT_API_KEY` defaults to public `local-dev-key` | Set strong random secret in `.env` |
| B2 | No ChatGPT capture mounted | Add `secrets/accounts/<alias>/chatgpt-request.txt` via console/CLI |
| B3 | No TLS / CORS `*` / single shared key | Keep off public internet; front with reverse proxy + TLS |

---

## 7. Environment-Variable Matrix

Derived from `Dockerfile`, `docker-compose.yml`, `.env.example`,
`apps/character-game/.env.example`, `cli.py`, and `crypto.py`. Secret values
are never printed.

| Variable | Component | Required | Purpose | Development Example | Production Requirement | Secret |
| --- | --- | :-: | --- | --- | --- | :-: |
| `CHATGPT_API_KEY` | API + game + clients | yes (for auth) | Shared Bearer token | `local-dev-key` | **Strong random secret; never `local-dev-key`** | yes |
| `CHATGPT_API_HOST` | API | yes | Bind host | `127.0.0.1` | `0.0.0.0` in Docker (or behind proxy) | no |
| `CHATGPT_API_PORT` | API | yes | API port | `8000` | `8000` | no |
| `CHATGPT_PUBLIC_BASE_URL` | API | yes | Artifact download URL base | `http://127.0.0.1:8000/v1` | **Host/LAN-reachable URL** (e.g. `https://<PRODUCTION_HOST>/v1`) | no |
| `CHATGPT_ACCOUNTS_DIR` | API | yes | Capture directory | `./secrets/accounts` | `/data/secrets/accounts` (volume) | no |
| `CHATGPT_ACCOUNT` | API | no | Primary alias | blank | blank (auto-discover) | no |
| `CHATGPT_ACCOUNTS` | API | no | Pinned alias list | blank | blank or explicit list | no |
| `CHATGPT_ACCOUNT_STRATEGY` | API | no | Routing strategy | `auto` | `failover` (Docker default) | no |
| `CHATGPT_IMAGE_OUTPUT_DIR` | API | yes | Image output dir | `./outputs/chatgpt-images` | `/data/outputs/chatgpt-images` | no |
| `CHATGPT_RESEARCH_OUTPUT_DIR` | API | yes | Research output dir | `./outputs/chatgpt-research` | `/data/outputs/chatgpt-research` | no |
| `CHATGPT_ADMIN_DB_PATH` | API | yes | SQLite path | `./outputs/chatgpt-admin.sqlite` | `/data/outputs/chatgpt-admin.sqlite` | no |
| `CHATGPT_AGENT_MODE` | API | no | Tool-bridge prompt mode | `optimized` | `optimized` | no |
| `CHATGPT_MODEL_FALLBACK` | API | no | Fallback model | `auto` | `auto` | no |
| `CHATGPT_TEMPORARY_CHAT` | API | no | Temporary chat mode | `true` | `true` (false for Deep Research) | no |
| `CHATGPT_WEB_TIMEOUT` | API | no | Provider timeout (s) | `5400` | `5400` | no |
| `CHATGPT_CHAT_CONCURRENCY` | API | no | Chat throttle | `free=1,go=2,plus=3,pro=4` | keep or lower | no |
| `CHATGPT_UPLOAD_CONCURRENCY` | API | no | Upload throttle | `free=1,...` | keep | no |
| `CHATGPT_IMAGE_CONCURRENCY` | API | no | Image throttle | `free=1,go=1,plus=2,pro=3` | keep or lower | no |
| `CHATGPT_RESEARCH_CONCURRENCY` | API | no | Research throttle | `free=1,go=1,plus=2,pro=2` | keep | no |
| `CHATGPT_CONSOLE_URL` | API | no | Console URL reported by API | `http://127.0.0.1:8080` | host URL | no |
| `CHATGPT_CONSOLE_COMMAND` | API | no | Console launch cmd | `docker compose up -d bridge-console` | as-is | no |
| `CHATGPT_SECRETS_PASSPHRASE` | API (crypto) | no | Non-interactive capture passphrase | unset | set for headless Docker (weaker; can leak via env/process list) | **yes** |
| `BRIDGE_CONSOLE_PORT` | Compose | no | Console host port | `8080` | `8080` | no |
| `CHARACTER_GAME_PORT` | Compose | no | Game host port | `3000` | `3000` | no |
| `CHATGAME_OPENAI_BASE_URL` | game (server-side) | yes | Bridge URL (container-internal) | `http://127.0.0.1:8000/v1` | `http://chatgpt-api:8000/v1` | no |
| `CHATGAME_PUBLIC_OPENAI_BASE_URL` | game (browser) | yes | Browser-facing bridge URL | `http://127.0.0.1:8000/v1` | derived from `CHATGPT_PUBLIC_BASE_URL` | no |
| `CHATGAME_OPENAI_API_KEY` | game | yes | Bridge Bearer key | `local-dev-key` | strong secret (mirrors `CHATGPT_API_KEY`) | yes |
| `CHATGAME_CHAT_MODEL` | game | no | Story model | `chatgpt-web/auto` | as-is | no |
| `CHATGAME_IMAGE_MODEL` | game | no | Scene-art model | `chatgpt-web/auto` | as-is | no |
| `CHATGAME_DB_PATH` | game | yes | Game SQLite path | `.data/arcadia.sqlite` | `/data/chatgame.sqlite` | no |
| `CHATGAME_IMAGE_DIR` | game | yes | Game image cache | `.data/images` | `/data/images` | no |
| `CHATGAME_AI_MODE` | game | no | `live`/`mock` | `live` | **`live`** (never `mock` in prod) | no |

### Flags raised

- **In `.env.example` but unused by runtime core:** `CHATGPT_ACCESS_TOKEN`,
  `CHATGPT_PROOF_TOKEN`, `CHATGPT_TURNSTILE_TOKEN`, `CHATGPT_COOKIES_JSON`,
  `CHATGPT_HEADERS_JSON`, `CHATGPT_HAR_PATH`, `CHATGPT_REQUEST_PATH` — these
  reference a legacy single-token/HAR capture flow; live captures come from
  `secrets/accounts/<alias>/chatgpt-request.txt` (paste/cURL import). They are
  legacy/diagnostic and not required by the Compose stack. **Stale but
  harmless.**
- **Used in code but absent from `.env.example`:** `CHATGPT_SECRETS_PASSPHRASE`
  (read in `crypto.py:24`) — documented in README security notes but missing
  from `.env.example`. Add it (commented) to the template.
- **Insecure defaults:** `CHATGPT_API_KEY=local-dev-key`,
  `CHATGAME_OPENAI_API_KEY=local-dev-key` — both publicly known; must override.
- **Browser-exposed:** `CHATGAME_PUBLIC_OPENAI_BASE_URL` is intentionally
  browser-facing (download/UI links) — that is by design; it must not carry a
  secret. `CHATGPT_API_KEY` is **not** browser-exposed (game uses it
  server-side only).
- **Build-time vs runtime:** none of these are build-time secrets; the
  Dockerfiles bake in defaults but Compose/runtime env overrides them. Captures
  are mounted at runtime, never baked.
- **`CHATGPT_SECRETS_PASSPHRASE`** is flagged secret — if used headless, treat
  its env exposure as a risk (prefer prompt mode where a TTY exists).

---

## 8. Target Deployment Topology

### Verified intended topology (from repo evidence)

**Docker Compose, single host, three services** — established by
`docker-compose.yml` and `docs/DOCKER.md`:

```text
[ Host ]
  chatgpt-api      (python:3.12-slim)  :8000  -> /v1, /health
  bridge-console   (nginx:alpine)      :8080  -> static dist/
  character-game   (node:22-trixie-slim):3000 -> SvelteKit node build
  volumes: ./secrets/accounts, ./outputs, ./outputs/character-game
```

This is the only topology the repo's tooling supports. The project explicitly
scopes itself to a **local / private-LAN** bridge, not a hosted service.

### Recommended (if the operator needs more than Compose)

1. **Recommended: single-host Docker Compose behind a reverse proxy (Caddy /
   nginx) with TLS** — adds HTTPS and a single public entrypoint without
   changing the app. Minimal architectural change: one proxy container + TLS
   certs; `CHATGPT_PUBLIC_BASE_URL` set to the HTTPS URL.
2. **Alternative: Linux systemd units running `python -m chatgpt_api serve`,
   `node build/index.js`, and a static console** — avoids Docker but loses the
   `HEALTHCHECK` and volume isolation; requires the operator to manage Python
   3.11+, Node 22, and nginx themselves.

Both are **recommendations**, not verified project intent. Kubernetes/IIS/
Vercel/Azure App Service are **not** supported by any repo configuration and
would require new manifests.

---

## 9. Complete Deployment Runbook

**Scope:** private single-host / LAN, Docker Compose. OS: Linux host
recommended (the `0o600` capture-key permission test only fails on Windows;
production captures should live on a Unix filesystem). Shell: `sh`/`bash`.
Privilege: non-root operator with `docker` group membership; `sudo` only where
noted.

> Replace every `<PLACEHOLDER>` before running. Never paste real captures or
> secrets into shared channels.

### 1. Prerequisites

1. Linux host (or WSL2 on Windows), 2 vCPU / 2 GB RAM minimum for a single
   small account; more for multiple Pro accounts with image/research load.
2. Docker Engine + Docker Compose v2 (`docker --version`, `docker compose version`).
3. Python 3.11+ and `bun` on the host (only to run host-side CLI/doctor and
   frontend re-validation; not required to run the containers).
4. Persistent disk for `./secrets` and `./outputs`.
5. At least one ChatGPT account you are authorized to use, captured per
   `docs/ACCOUNT_CAPTURE.md`.

### 2. Required runtime and tool versions

```sh
# sh/bash, repo root, operator user (docker group)
docker --version          # Docker 24+
docker compose version    # v2.x
python3 --version         # 3.11+
bun --version             # optional, for frontend re-validation
```

### 3. Server sizing assumptions

- Single Free account: 2 vCPU / 2 GB RAM.
- Multiple Pro accounts with image/research load: 4 vCPU / 4 GB RAM.
- Disk: 10 GB+ for `outputs/` artifacts; captures are kilobytes each.

### 4. DNS and hostname preparation

- For LAN: reserve `<PRODUCTION_HOST>` (e.g. `chatgpt-bridge.lan`) on internal
  DNS or use the host LAN IP.
- For TLS: point a real hostname at the host if using Let's Encrypt.

### 5. TLS/HTTPS preparation

The repo provides **no TLS**. Put a reverse proxy (Caddy/nginx) in front, or
accept HTTP on a trusted LAN only. `HTTPS=<not provided by repo>`.

### 6. Firewall and port requirements

- Open (LAN only): `8000` (API), `8080` (console), `3000` (game).
- **Do not** expose these to a public network without a proxy + strong key.
  Docker binds the API to `0.0.0.0` inside the container; host port publishing
  is what makes it reachable — keep the host firewalled.

### 7. Service-account requirements

- One Linux operator account in the `docker` group.
- No cloud service accounts required (no external storage, no managed DB).

### 8. Database creation

- **No external DB.** SQLite files auto-created:
  - `outputs/chatgpt-admin.sqlite` (bridge admin)
  - `outputs/character-game/chatgame.sqlite` (game, via volume
    `./outputs/character-game:/data`)
- Ensure `./outputs` is writable by uid 10001 (`appuser`) for the API
  container, and by the node image uid for the game.

### 9. Database backup preparation

```sh
# sh/bash, repo root, operator user
cp .env.example .env
mkdir -p secrets/accounts outputs outputs/character-game
tar czf backup-predeploy-$(date +%Y%m%d).tgz outputs secrets/accounts .env
# Store this archive off-host.
```

### 10. Database migration procedure

- **No explicit migration command.** `BridgeAdminStore._migrate()` runs in the
  constructor on first request and is idempotent
  (`CREATE TABLE IF NOT EXISTS`). Starting the API container is the migration.
- After first boot, verify tables exist (read-only):

```sh
sqlite3 outputs/chatgpt-admin.sqlite ".tables"
# Expected: artifacts  account_captures  settings
```

### 11. Object/file storage preparation

```sh
mkdir -p outputs/chatgpt-images outputs/chatgpt-research outputs/character-game
# Bind-mounted into containers; ensure host fs permissions allow container uids
# to write.
```

### 12. Environment-variable configuration

```sh
cp .env.example .env
# Edit .env: set at minimum
#   CHATGPT_API_KEY=<STRONG_RANDOM_SECRET>
#   CHATGPT_PUBLIC_BASE_URL=http://<PRODUCTION_HOST>:8000/v1   (or https via proxy)
# Leave CHATGPT_ACCOUNT/CHATGPT_ACCOUNTS blank to auto-discover captures.
```

Generate a strong key:

```sh
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
# Paste output into .env as CHATGPT_API_KEY=<that value>
```

### 13. Secret-management procedure (captures)

- Captures are **credentials**. Add via the running console/CLI (step 23) or
  place the encrypted file directly under
  `secrets/accounts/<alias>/chatgpt-request.txt` on the host.
- For headless Docker, set
  `CHATGPT_SECRETS_PASSPHRASE=<PASSPHRASE>` in `.env` (mind env exposure), or
  use `--secrets-passphrase-prompt` when starting interactively.
- Verify `secrets/` stays ignored:

```sh
git check-ignore secrets/accounts   # must print the path (ignored)
```

### 14. Dependency installation (host tooling only)

```sh
python3 -m pip install -e '.[dev]'   # optional: host CLI/doctor access
```

### 15. Application build / 16. Artifact / container creation

```sh
# Validate Compose (non-destructive)
docker compose config --quiet
# Build all three images (does not start services)
docker compose build
```

Expected: three images build with no errors (`chatgpt-api:local`,
`chatgpt-bridge-console:local`, `chatgpt-character-game:local`).

### 17–19. Frontend / backend / worker deployment

No separate worker service. All three services deploy together via Compose
(next step). Console = static (nginx); game = node server; API = backend.

### 20. Reverse-proxy configuration

Not provided by the repo. If exposing beyond one trusted LAN machine, place
Caddy/nginx in front and set `CHATGPT_PUBLIC_BASE_URL` to the proxy's HTTPS
URL. Otherwise skip.

### 21. Authentication configuration

- The only auth is `CHATGPT_API_KEY`. Ensure `.env` has the strong secret from
  step 12. Clients pass `Authorization: Bearer <CHATGPT_API_KEY>`.
- No tenant/issuer/OAuth to configure.

### 22. CORS and trusted-origin configuration

- CORS is hardcoded `*` (`http_utils.py:34`). **No env knob** to restrict
  origins. Accept for a trusted LAN, or patch the code (out of scope for this
  runbook) before any wider exposure.

### 23. Service startup

```sh
# sh/bash, repo root, operator user (docker group)
docker compose up -d --build
docker compose ps
```

Expected: all three services `Up`. API `HEALTHCHECK` turns healthy within
~10s.

### 24. Service persistence and automatic restart

- `restart: unless-stopped` is set for all three services in
  `docker-compose.yml` — containers restart on failure and on host reboot
  (assuming the Docker daemon is enabled at boot).
- Keep `./secrets/accounts` and `./outputs` on the same host paths to survive
  rebuilds.

### 25. Health and readiness verification

```sh
curl -sS -H "Authorization: Bearer <CHATGPT_API_KEY>" http://127.0.0.1:8000/health
curl -sS -H "Authorization: Bearer <CHATGPT_API_KEY>" http://127.0.0.1:8000/v1/models
curl -sS http://127.0.0.1:8080/health        # -> ok
curl -sS http://127.0.0.1:3000/api/status
docker compose ps
```

Expected: `/health` JSON, `/v1/models` list, console `ok`, game status JSON,
all services healthy.

### 26. Post-deployment smoke tests

```sh
# No capture yet: /health and /v1/models pass; chat returns an auth/provider error.
# Add a capture first (CLI paste flow):
docker compose exec -it chatgpt-api chatgpt-api admin account add \
  --account <ALIAS> --paste \
  --base-url http://127.0.0.1:8000/v1 --api-key <CHATGPT_API_KEY>
# (paste copied Network request / cURL capture, then a line: END_CAPTURE)

docker compose exec chatgpt-api chatgpt-api admin capacity \
  --base-url http://127.0.0.1:8000/v1 --api-key <CHATGPT_API_KEY>

curl -sS -X POST http://127.0.0.1:8000/v1/chat/completions \
  -H "Authorization: Bearer <CHATGPT_API_KEY>" -H "Content-Type: application/json" \
  --data-raw '{"model":"auto","messages":[{"role":"user","content":"Reply with exactly: bridge ok"}]}'
```

Expected: chat returns `bridge ok` (or the model's reply) once a capture is
loaded.

### 27. Authentication and authorization tests

```sh
# expect 401 (no key), 401 (wrong key), 200 (correct key)
curl -sS -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/v1/models
curl -sS -o /dev/null -w "%{http_code}\n" -H "Authorization: Bearer wrong" http://127.0.0.1:8000/v1/models
curl -sS -o /dev/null -w "%{http_code}\n" -H "Authorization: Bearer <CHATGPT_API_KEY>" http://127.0.0.1:8000/v1/models
```

### 28. File upload/download tests

```sh
IMG=$(curl -sS -X POST http://127.0.0.1:8000/v1/images/generations \
  -H "Authorization: Bearer <CHATGPT_API_KEY>" -H "Content-Type: application/json" \
  --data-raw '{"model":"gpt-image-1","prompt":"small blue app icon, no text","n":1}')
# extract download_url from $IMG, then:
curl -sS -o /tmp/icon.png -L "<DOWNLOAD_URL_FROM_RESPONSE>" -H "Authorization: Bearer <CHATGPT_API_KEY>"
file /tmp/icon.png   # expect an image
```

### 29. Database read/write tests

```sh
# The image smoke above already writes an artifact row. Verify:
sqlite3 outputs/chatgpt-admin.sqlite "SELECT file_id, kind, created_at FROM artifacts ORDER BY created_at DESC LIMIT 5;"
```

### 30. Logging and monitoring validation

```sh
docker compose logs --tail=50 chatgpt-api
# Confirm: redacted summaries only (no raw Authorization, cookies, or capture text).
```

No metrics/telemetry integration; monitoring = `docker compose ps` + log tails
+ `/health` and `/v1/chatgpt/usage`.

### 31. Backup validation

```sh
tar czf backup-postdeploy-$(date +%Y%m%d).tgz outputs secrets/accounts .env
# Restore-test on a throwaway host: unpack, docker compose up, verify /health + /v1/models.
```

### 32. Rollback procedure

See §12.

### 33. Deployment acceptance checklist

- [ ] `.env` has a strong `CHATGPT_API_KEY` (not `local-dev-key`).
- [ ] `CHATGPT_PUBLIC_BASE_URL` is host/LAN-reachable.
- [ ] At least one capture loaded and `admin capacity` shows it.
- [ ] `/health` and `/v1/models` return 200.
- [ ] Wrong-key request returns 401.
- [ ] A chat smoke returns a real reply.
- [ ] An image generation returns a downloadable URL that resolves.
- [ ] `outputs/chatgpt-admin.sqlite` has the artifact row.
- [ ] Logs show redacted summaries only.
- [ ] Pre-deploy and post-deploy backups exist off-host.

---

## 10. Post-Deployment Validation

Re-run the 2026-06-26 snapshot gates on the deploy host (the snapshot was
recorded on a Unix-like system; this audit host is Windows, so re-running on
the deploy host matters):

```sh
python3 -m compileall chatgpt_api tests
python3 -m pytest -q                       # expect all tests except the known Windows perm fail
bun run --cwd apps/bridge-console check && bun run --cwd apps/bridge-console build
bun run --cwd apps/character-game check && bun run --cwd apps/character-game test && bun run --cwd apps/character-game build
docker compose config --quiet
```

Live (capture-dependent):

```sh
curl -H "Authorization: Bearer <CHATGPT_API_KEY>" http://127.0.0.1:8000/health
curl -H "Authorization: Bearer <CHATGPT_API_KEY>" http://127.0.0.1:8000/v1/models
curl -X POST ... /v1/chat/completions   # bridge ok
curl -X POST ... /v1/images/generations # download_url resolves
```

---

## 11. Monitoring and Backup

- **Monitoring:** no built-in metrics. Use `docker compose ps`,
  `docker compose logs -f chatgpt-api`, and `GET /health`,
  `GET /v1/chatgpt/usage` on a schedule. Alert on container `restart_count`
  rising or `/health` non-200.
- **Backup (operator-manual, no automation in repo):**
  - `outputs/chatgpt-admin.sqlite` (artifact/account/settings metadata)
  - `outputs/chatgpt-images/`, `outputs/chatgpt-research/` (generated files)
  - `outputs/character-game/` (game DB + image cache)
  - `secrets/accounts/` (encrypted captures — treat as credentials)
- **Schedule:** daily tarball off-host; snapshot immediately before any
  `docker compose up --build` upgrade.

---

## 12. Rollback Plan

### Rollback triggers

- API `/health` non-200 for >2 min after deploy.
- All chat/image/research calls failing where they worked before.
- Capture decryption errors after an upgrade (`wrong CHATGPT_SECRETS_PASSPHRASE`
  / re-encryption mismatch).
- Container `restart_count` climbing uncontrollably.

### Application rollback steps

```sh
# sh/bash, repo root, operator user (docker group)
docker compose down
tar xzf backup-predeploy-<DATE>.tgz -C <REPO_ROOT>   # restore outputs/, secrets/accounts/, .env
git checkout <PREVIOUS_COMMIT>
docker compose build
docker compose up -d
```

### Database rollback constraints

- The schema migration is **additive and idempotent only**
  (`CREATE TABLE IF NOT EXISTS`, `INSERT OR REPLACE`); there is **no
  destructive migration** and **no down-migration** in the repo. A newer
  schema is forward-compatible; rolling back the code to an older commit on a
  newer-schema DB is generally safe because the schema only adds tables/columns
  that older code ignores.
- **Do not** manually `DROP` tables to "roll back" the schema — it is not
  required and will lose artifact metadata. If a schema rollback is ever
  needed, restore the pre-deploy `chatgpt-admin.sqlite` from the backup
  tarball instead.
- **Verified limitation:** the repo does not provide a down-migration tool, so
  a true schema-reversal is **not verified as supported**. File restore is the
  only safe path.

### Storage rollback considerations

- Generated artifacts in `outputs/` are not versioned; restoring the backup
  tarball is the only rollback. Files created after the backup snapshot are
  lost unless re-snapshotted.
- Captures: if you rotated encryption mode (`secrets rotate`) as part of the
  deploy, the old key file / passphrase is gone — restore the pre-rotate
  `secrets/accounts/` from backup to use old-format captures again.

### Configuration rollback

- `.env` is in the backup tarball; restoring it reverts env changes (key,
  base URL, strategy). Keep the strong `CHATGPT_API_KEY` — do not revert it to
  `local-dev-key`.

### Verification after rollback

```sh
docker compose ps
curl -H "Authorization: Bearer <CHATGPT_API_KEY>" http://127.0.0.1:8000/health
curl -X POST ... /v1/chat/completions   # confirm a real reply
```

---

## 13. Open Decisions

1. **Deployment boundary:** private LAN only, or also behind a reverse proxy
   with TLS? The repo supports neither TLS nor restricted CORS in code.
2. **Secrets mode for headless Docker:** `CHATGPT_SECRETS_PASSPHRASE` (env,
   weaker) vs. mounting a pre-encrypted `secrets/` with the auto key file
   (key sits next to data). Pick one and document it for the operator.
3. **Capture refresh cadence:** captures expire ~10 days; decide weekly
   rotation vs. on-failure refresh.
4. **Whether to add a `character-game` Docker `HEALTHCHECK`** (currently
   absent — small hardening task).
5. **Whether to add CI** (`.github/` is absent) to gate releases beyond the
   manual snapshot.

---

## 14. Recommended Next Task

**Add a reverse-proxy + TLS option and a restricted-CORS env knob** so the
stack can be safely exposed beyond a single trusted loopback host — the
single largest gap between "works on a LAN laptop" and "safe private-server
deployment." Concretely: a Caddy/nginx compose service documented in
`docs/DOCKER.md` and a `CHATGPT_ALLOWED_ORIGINS` env var read in
`http_utils.send_cors_headers` (currently hardcoded `*`).

This is the highest-leverage hardening step that stays inside the project's
"local/private bridge" scope without attempting the out-of-scope multi-tenant
production layer.
