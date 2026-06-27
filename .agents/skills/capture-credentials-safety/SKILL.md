---
name: capture-credentials-safety
description: "Mandatory guard for any task that reads, writes, parses, encrypts, decrypts, migrates, displays, exports, deletes, tests, or troubleshoots ChatGPT account captures or authentication material. Enforces capture-as-credential rules: never expose live secrets, never commit captures, never log tokens/cookies/keys, never weaken encryption or file-permission controls, never use real captures in tests."
allowed-tools:
  - Read
  - Grep
  - Glob
  - Bash
  - Edit
  - Write
  - TaskStop
---

# capture-credentials-safety

> Repository-local skill for `chatgpt-api`. Grounded in code on 2026-06-27.
> When this skill and the code disagree, trust the code (`AGENTS.md` §0).
> This skill **references** authoritative files; it does not duplicate them.

## 1. Purpose

Protect captured ChatGPT credentials and authentication material throughout
implementation, testing, review, and troubleshooting. A capture is a **live
ChatGPT browser session** — cookies, bearer tokens, and sentinel/proof
headers. It is a credential, not test data. This skill prevents leaks via
logs, commits, prompts, fixtures, screenshots, reports, or "helpful" debug
output, and prevents weakening of the encryption, file-permission, and
Git-exclusion controls that protect captures at rest.

## 2. Mandatory Triggers

Invoke this skill **before** making changes when a task involves any of:

**Direct capture/auth changes:**
- capture import / add / update / verify / delete flows (CLI `admin account
  add|update|verify|delete`, `admin save-capture`, HTTP
  `/v1/chatgpt/admin/captures/*`, `/accounts/*`)
- capture file format or parsing (`request_capture.py`)
- encryption / decryption / key management (`crypto.py`, `secrets rotate`)
- authentication code (`auth.py`, `ChatGPTAuthConfig`)
- token, cookie, or session handling / refresh
- transport that replays captured headers (`transport.py`)

**Indirect changes (frequently missed):**
- SQLite fields holding capture metadata (`account_captures` table in
  `admin_store.py`)
- logging, error messages, or debug output near any credential path
- export, backup, migration, or restore behavior
- tests or fixtures for capture flows
- file-permission code or `.gitignore` / `.dockerignore`
- API responses that may contain auth info (`/usage`, `/admin/accounts`,
  operation inspect, artifact download)
- reviewing a PR/diff that touches any of the above

If any trigger applies, **stop and classify the task** (§6) before editing.

## 3. Non-Negotiable Rules

1. **Never display or reproduce a live credential value** — token, cookie,
   key, passphrase, or decrypted capture — in a prompt, message, log, error,
   screenshot, fixture, report, doc, or comment.
2. **Never place real credentials in** prompts, logs, errors, stack traces,
   screenshots, fixtures, reports, or documentation. Use redacted
   fingerprints / counts / structural descriptions instead.
3. **Never commit** captures, decrypted payloads, `.master.key`,
   `.master.salt`, cookies, tokens, session files, `.env`, or `*.har`.
4. **Never use a real capture for automated testing.** Synthetic data only.
5. **Never weaken encryption, authentication, file-permission, or
   Git-exclusion controls** merely to make a test pass. Do not "fix" the
   Windows `0o600` test by relaxing the permission (see §11 caveat).
6. **Never treat a development-only auth shortcut as production behavior.**
   The legacy single-token env vars (`CHATGPT_ACCESS_TOKEN`,
   `CHATGPT_PROOF_TOKEN`, `CHATGPT_TURNSTILE_TOKEN`, `CHATGPT_COOKIES_JSON`)
   and `CHATGAME_AI_MODE=mock` are dev/diagnostic only.
7. **Never print complete sensitive objects for debugging.** Reuse the
   repo's redaction utilities (§8) rather than dumping dicts.
8. **Never invent successful validation** that was not run. Mark unavailable
   checks `NOT RUN` with a reason.
9. **Never run destructive capture operations** (delete, rotate, overwrite)
   without explicit task scope and a confirmed backup/rollback path.
10. **Never expose secret values in the completion report.** Names and paths
    only, never values.

## 4. Sensitive Data Classification

Map fields to categories. Use **names, counts, hashes, redacted fingerprints,
timestamps, or structural descriptions** — never values.

**Secret (never log/commit/display):**
- `authorization` header (Bearer access token)
- `cookie` header and parsed `cookies` dict
- `openai-sentinel-proof-token`, `openai-sentinel-turnstile-token`,
  `openai-sentinel-chat-requirements-token`, `x-conduit-token`
- `ChatGPTAuthConfig.access_token`, `.proof_token`, `.turnstile_token`,
  `.cookies`
- `.master.key` and `.master.salt` contents
- `CHATGPT_SECRETS_PASSPHRASE` and the runtime passphrase
- decrypted capture plaintext; `chatgpt-request.txt` body before encryption

**Sensitive authentication metadata (mask before display):**
- account alias; `email` (use `mask_email`); `account_id`, `user_id`
  (use `mask_id`); `capture_path`; `plan_type`
- the set of present/absent sentinel header **names** (ok to list names; not
  values)

**Safe operational metadata (ok to show):**
- cookie **count**; capabilities JSON; checks JSON; model alias; `action`;
  URL host; artifact `file_id`/`filename`/`bytes`

**Public/non-sensitive:**
- route shapes, model alias names, CLI command names (as documented)

## 5. Required Reading

Read these **authoritative** files before any capture-related change (do not
rely on memory):

- `AGENTS.md` §8 (roles/auth), §11 (DB), §16 (security constraints), §17 (Windows caveat)
- `docs/ACCOUNT_CAPTURE.md`
- `chatgpt_api/providers/chatgpt/crypto.py` — encryption, key sources, rotate
- `chatgpt_api/providers/chatgpt/request_capture.py` — `SECRET_HEADER_NAMES`,
  `CapturedRequest.from_file`, `redacted_headers`
- `chatgpt_api/providers/chatgpt/auth.py` — `ChatGPTAuthConfig`
- `chatgpt_api/api/openai_compat.py` — `_save_account_capture_payload`
  (~line 2680), `_inspect_account_capture` (~2720), `_redacted_headers`
  (~2842), `_unlink_expected_account_file` (~2660), `_public_status_error`
  (~4370)
- `chatgpt_api/api/admin_store.py` — `account_captures` schema +
  `record_account_capture` / `delete_account_capture`
- `.gitignore` and `.dockerignore`
- `tests/test_crypto.py`, `tests/test_request_capture.py`,
  `tests/test_chatgpt_auth.py`

## 6. Pre-Change Safety Assessment

Before editing, determine and record:

- what sensitive material the change touches (classify per §4)
- whether plaintext is introduced anywhere (memory, temp file, log, response)
- whether logging or error behavior changes near credential paths
- whether persistence behavior changes (capture file, SQLite metadata, key files)
- whether encryption boundaries change (key source, prefix `enc:v1:`, PBKDF2)
- whether Git-tracked paths change
- whether test data stays synthetic
- whether platform-specific permission behavior is affected (Windows `0o600`)
- whether backward compatibility is affected (legacy plaintext passthrough,
  encrypted-file format)
- whether migration/rollback is required (rotate re-encrypts in place; no
  down-migration exists for SQLite)

**Risk classification criteria:**
- **Low** — docs/comment only; no code path that handles secrets.
- **Medium** — touches redaction, inspection display, or SQLite metadata
  fields; no change to encryption or key handling.
- **High** — touches capture save/load, `SECRET_HEADER_NAMES`, logging near
  credential paths, or file permissions.
- **Critical** — touches `crypto.py` key derivation/encryption, the `enc:v1:`
  format, `secrets rotate`, or any path that could write plaintext to disk.

## 7. Safe Implementation Procedure

1. Read the §5 required sources.
2. Trace the current credential data flow (save → encrypt → store → load →
   decrypt → `ChatGPTAuthConfig` → transport).
3. Classify affected data (§4).
4. Identify trust boundaries (disk, memory, logs, HTTP responses, Git).
5. Check encryption and persistence implications (no plaintext at rest; key
   source unchanged unless intended).
6. Check logging and error paths (reuse redaction utilities).
7. Check Git and artifact exclusion (`git check-ignore`).
8. Implement the smallest coherent change; reuse existing patterns.
9. Use only synthetic test data (§9).
10. Run the required security and functional checks (§11).
11. Inspect the diff for accidental disclosure (grep diff for header names,
    `Bearer`, `enc:v1:`, passphrases).
12. Update only the required documentation (per `AGENTS.md` §15).
13. Produce a redacted completion report (§15).

## 8. Logging and Error-Handling Rules

- No complete token, cookie, key, capture, header, or decrypted payload in
  any log, error, stack trace, or debug context.
- **Reuse the repo's redaction utilities**, do not write new ones:
  - `CapturedRequest.redacted_headers()` / `_redacted_headers()` → replace
    `SECRET_HEADER_NAMES` values with `<redacted>`
  - `AccountInfo.to_redacted_dict()` → `mask_email` / `mask_id`
  - `_public_status_error(exc)` → sanitize exceptions for display
- Show cookie **counts**, not cookie values.
- Never serialize a `CapturedRequest` or `ChatGPTAuthConfig` to JSON/str for
  logging without redaction.
- No secret values in test snapshots or golden files.

## 9. Test Data Rules

- Synthetic credentials only — clearly invalid, non-production values
  (e.g. `Bearer fake-token`, `not-a-real-session`).
- No copied browser cookies or tokens; no capture derived from a real
  session.
- Deterministic fixtures where possible; place under `tests/` only.
- No fixture that looks like a real credential (no realistic JWT/cookie
  shapes when a simpler invalid placeholder suffices).
- Clean up temporary capture files, temp DBs, and artifacts after the test.
- Tests must prove behavior without contacting a real ChatGPT account.

## 10. Git and Artifact Safety

Do not assume a filename is ignored because it looks secret. **Verify:**

- `git check-ignore -v <path>` for any capture/key/temp file you create.
- `git status` after the change — confirm no unintended files appear.
- Generated files under `outputs/`, `*.har`, `chatgpt-request.txt`,
  `*chatgpt-request*.txt`, `.master.key`, `.env` must stay ignored.
- Temp files, DB copies, backup files, screenshots, and reports must not
  leak secrets; clean them up.

`.gitignore` covers: `secrets/`, `.env`, `*.har`, `chatgpt-request.txt`,
`*chatgpt-request*.txt`, `*.sqlite*`. `.dockerignore` mirrors secret paths.

## 11. Validation Matrix

Based on `AGENTS.md` §14. Run the matching subset for the change type:

| Change type | Commands (repo root) |
| --- | --- |
| Crypto / encryption | `python -m pytest tests/test_crypto.py -q` |
| Capture parsing | `python -m pytest tests/test_request_capture.py -q` |
| Auth / token handling | `python -m pytest tests/test_chatgpt_auth.py -q` |
| SQLite metadata | `python -m pytest tests/test_admin_store.py -q` |
| Logging / API response near auth | `python -m pytest tests/test_openai_compat.py -q` |
| Any backend change | `python -m compileall chatgpt_api` then `python -m pytest -q` |
| Docs-only | no automated gate; re-read affected doc |

For unavailable tools/services, report `NOT RUN` with the reason — never
claim success. Do not run `docker compose up` (deploy action). Do not run
destructive pytest.

**Windows file-permission caveat (document, do not "fix"):**
`tests/test_crypto.py::test_load_secrets_key_creates_owner_only_key_file`
asserts the `.master.key` mode is `0o600`. On Windows NTFS the mode returns
`0o666` (438), so this single test **fails on Windows**. This is a
platform/test mismatch (`AGENTS.md` §17), **not a code defect**. Do not relax
the `os.open(..., 0o600)` permission to make it pass — `0o600` is correct
POSIX behavior. All other crypto tests pass.

## 12. Dry-Run Validation Procedure

Use a throwaway synthetic capture (no real credential). Derive commands from
the repo; do not invent them.

1. Use a temp `accounts_dir` (e.g. `mktemp -d`) and a synthetic alias
   (e.g. `synthetic-dryrun`).
2. Build a synthetic capture text with clearly fake values:
   `Authorization: Bearer fake-token`, a fake `Cookie:`, a chatgpt.com URL,
   and a minimal request JSON. Never reuse a real token format.
3. Encrypt via the repo path:
   `python -c "from chatgpt_api.providers.chatgpt.crypto import encrypt_text, load_secrets_key; ..."`
   writing to `<accounts_dir>/<alias>/chatgpt-request.txt`.
4. Assert the on-disk content starts with `enc:v1:` and the plaintext value
   (`fake-token`) does **not** appear in the file. Use a grep / boolean
   assertion — do not print the value.
5. Load via `CapturedRequest.from_file` and assert `redacted_headers()`
   returns `<redacted>` for `authorization` and `cookie`.
6. `git check-ignore -v <path>` — must show the path is ignored; if not,
   **stop and report a critical issue**.
7. Run the §11 crypto/auth tests.
8. Delete all temp files; `git status` must show no unintended changes.
9. No external ChatGPT or production request may occur. Do not touch
   existing `secrets/accounts/` captures.

## 13. Stop Conditions

Stop implementation and report (without reproducing the triggering secret)
if:

- a real credential is encountered
- encryption behavior cannot be determined from code
- key management is ambiguous (which of the 3 sources is active)
- a capture path is Git-tracked (not ignored)
- tests require live credentials to pass
- a requested change would write plaintext to disk
- a requested change disables encryption, file-permission, or Git-exclusion
  controls
- the code conflicts with current security documentation
- destructive migration (rotate/delete) lacks a backup or rollback strategy
- required validation cannot be performed and the risk is High or Critical

## 14. Review Checklist

- [ ] Data classified (§4); no secret value printed
- [ ] Encryption boundary unchanged (or intentionally changed + tested)
- [ ] No plaintext at rest, in logs, in errors, or in responses
- [ ] Logging reuses `redacted_headers` / `to_redacted_dict` / `_public_status_error`
- [ ] Error responses sanitized
- [ ] Tests use synthetic data only; no real capture
- [ ] `git check-ignore` confirms new paths ignored; `git status` clean
- [ ] File permissions: `0o600` preserved; Windows caveat documented not "fixed"
- [ ] SQLite metadata stores masked fields only; no credential blob
- [ ] Temp files cleaned up
- [ ] Backward compatibility preserved (legacy plaintext passthrough, `enc:v1:` format)
- [ ] Rollback path identified (file restore; no SQLite down-migration exists)
- [ ] Documentation updated per §15 rules
- [ ] Completion report is redacted

## 15. Completion Report Format

Report (no secret values):

- **Objective** — what was to be done
- **Risk classification** — Low/Medium/High/Critical (§6) with rationale
- **Sensitive areas touched** — by category (§4), names only
- **Files changed** — every path
- **Safeguards preserved or added** — which redaction/crypto controls
- **Tests and commands run** — exact commands + PASS/FAIL/NOT RUN
- **Git/artifact checks** — `git check-ignore` / `git status` result
- **Unavailable validation** — what could not run and why
- **Remaining risks** — including the Windows caveat if relevant
- **Documentation updated** — which docs
