# Claude Code Skill Proposal — `chatgpt-api`

> Audit + proposal only. No skills were installed, downloaded, or created
> during this task. Verified against repository evidence on **2026-06-27**.
> When code and this document disagree, trust the code (`CLAUDE.md` §0).

---

## 1. Executive Summary

**Yes — this repository would benefit from a small set of project-specific
skills.** The codebase has unusually sharp, repeated, high-risk workflows that
generic skills and `CLAUDE.md` prose alone do not enforce reliably:

- **Account captures are live credentials** (encrypted at rest, never
  committed, never logged, expire ~10 days). Every add/update/verify/rotate
  touches this risk surface.
- **The SQLite schema lives inline in one method** (`admin_store._migrate`),
  with no migration framework, no down-migration, and an idempotency
  requirement. A careless schema edit silently breaks deploy safety.
- **The `/v1` API is "OpenAI-shaped" with documented contract gaps** that must
  not be silently "fixed." Route/response changes must be checked against a
  contract doc + a 5,580-line handler.
- **Validation is a change-type → command matrix** (`CLAUDE.md` §14) that
  agents routinely run incompletely (especially the frontend `bun` gates and
  the Windows test-permission caveat).
- **Documentation write-back is rule-bound** (`CLAUDE.md` §15) with a README
  validation snapshot that must stay truthful.

These are not generic concerns — they are specific to this repo's
provider-first, local-bridge architecture. `CLAUDE.md` already states the
rules, but rules in prose get skipped under time pressure; deterministic
skills turn them into repeatable, validated workflows.

**Recommended initial set: 5 skills** (one primary + four supporting), all
**CREATE** decisions, because no installed or public skill matches these
repo-specific constraints. The existing `gsd-*` and built-in `code-review` /
`security-review` skills overlap only generically and would need adaptation
that approximates writing them from scratch.

**First skill to implement:** `capture-credentials-safety` — highest risk,
highest frequency, most repo-specific.

---

## 2. Repository Needs Assessment

Discovered repeated workflows and risk areas (evidence in parentheses):

| Workflow / risk | Frequency | Risk | Where it is documented | Why agents lose it |
| --- | --- | --- | --- | --- |
| Add/update/verify/rotate a ChatGPT account capture without leaking or logging it | high | **critical** (credentials) | `CLAUDE.md` §16, `docs/ACCOUNT_CAPTURE.md`, `crypto.py` | scattered across CLI, console, crypto, and `.gitignore`/`.dockerignore` |
| Change the SQLite admin schema idempotently with no migration framework | medium | high | `CLAUDE.md` §11, `admin_store.py:_migrate` | the "no migration files, must stay idempotent" rule is easy to violate |
| Change a `/v1` route or response shape without breaking the OpenAI-shaped contract or "fixing" documented gaps | medium | high | `CLAUDE.md` §12, `docs/OPENAI_COMPATIBILITY.md`, `openai_compat.py` (~5.6k lines) | handler is monolithic; known gaps are listed in prose |
| Run the correct validation subset for a change type | high | medium | `CLAUDE.md` §14 | agents skip frontend gates or mis-handle the Windows `0o600` test |
| Write back the right docs + keep the README snapshot truthful | high | medium | `CLAUDE.md` §15 | many docs; easy to update the wrong one or skip the snapshot |
| Assess deployment readiness for a private-LAN Docker stack | low-medium | high | `docs/deployment/DEPLOYMENT_READINESS_AND_RUNBOOK.md` (new) | ad-hoc; no reusable gate |

**Context agents frequently lose:**

- That `references/legacy/OpenaiChat.py` is **not runtime** and imports absent
  deps (`CLAUDE.md` §17).
- That `CHATGAME_AI_MODE=mock`, unset key, and `local-dev-key` are
  **dev-only**, not production.
- That operation records are **in-memory only** and do not survive restart.
- That token usage returns **zero placeholders** — no billing logic should be
  built on it.
- That the only auth is a **single shared Bearer token**, no RBAC.

**Patterns requiring consistent execution:** idempotent schema edits,
parameterized SQL, redacted logging, never-bake-secrets, change-type-gated
validation, doc write-back to the exact affected files.

**Procedures scattered across multiple documents:** account capture safety
lives in `CLAUDE.md` §16 + `docs/ACCOUNT_CAPTURE.md` + `crypto.py` + two
ignore files — a prime skill candidate.

---

## 3. Existing Skill Discovery

**Locations searched:**

- Repository-local skills: `.claude/skills/` — **does not exist** (no `.claude/`
  directory in the repo).
- User skill directory: `~/.claude/skills/` — **present**, contains the
  `gsd-*` family (e.g. `gsd-code-review`, `gsd-add-tests`, `gsd-audit-fix`,
  `gsd-security-auditor`-adjacent tooling, `gsd-debug`, `gsd-docs-update`,
  `gsd-validate-phase`, `gsd-secure-phase`).
- Built-in / always-available skills visible in this session: `code-review`,
  `security-review`, `simplify`, `verify`, `run`, `init`, `deep-research`,
  `loop`, `update-config`, `keybindings-help`, `fewer-permission-prompts`.

**Existing candidates found and evaluated:**

| Candidate | Source | Purpose | Suitability for this repo |
| --- | --- | --- | --- |
| `gsd-code-review` / built-in `code-review` | user / built-in | Generic source review for bugs/security/quality | Overlaps *generically* with the contract guardian and capture-safety review, but knows nothing of OpenAI-shaped contracts, documented gaps, or capture-as-credential rules. Would need heavy adaptation. |
| `gsd-add-tests` | user | Generate tests for a completed phase | Overlaps with validation-runner, but is phase-oriented (GSD lifecycle), not change-type-oriented per `CLAUDE.md` §14. |
| `gsd-docs-update` | user | Update docs verified against codebase | Closest overlap with documentation-writeback; could be **adapted** but its lifecycle assumes GSD planning artifacts this repo does not have (`CLAUDE.md` §4 confirms no PROJECT.md/ROADMAP/etc.). |
| `gsd-secure-phase` / built-in `security-review` | user / built-in | Verify threat mitigations / security review of diff | Overlaps with capture-safety, but generic; does not encode the specific capture/crypto/logging rules. |
| `verify` / `run` | built-in | Run the app / verify a change works | Useful as a primitive the validation-runner could call, not a replacement. |

**Candidates rejected:**

- `gsd-docs-update` as-is: assumes GSD planning artifacts absent here → would
  need adaptation amounting to a rewrite.
- Any `gsd-*` lifecycle skill: this repo explicitly has no GSD planning dir
  and forbids inventing one (`CLAUDE.md` §4). Not a fit.
- `deep-research`, `loop`: not relevant to these workflows.

**Unavailable search mechanisms:**

- No Claude Code plugin/skill **registry search** tool is available in this
  environment beyond listing installed user skills.
- Public skill marketplaces were **not queried** (no registry tool; web search
  for arbitrary skills is unreliable and risks recommending untrusted code).
  Therefore no public skill is claimed as available.

**Trust/compatibility concerns:** any downloaded third-party skill would
execute in a repo that handles **live ChatGPT credentials**; blind download is
unacceptable. CREATE (repo-local, auditable) is strongly preferred over
DOWNLOAD for anything touching capture/crypto/auth paths.

---

## 4. Candidate Skill Matrix

Scoring 1–5 (5 = highest). `Priority = Frequency + RiskReduction + TimeSaved +
RepoSpecificity + EaseOfValidation − MaintenanceCost`.

| Skill | Decision | Frequency | Risk Reduction | Time Saved | Repository Specificity | Ease of Validation | Maintenance Cost | Priority Score |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `capture-credentials-safety` | CREATE | 5 | 5 | 4 | 5 | 4 | 2 | **21** |
| `sqlite-schema-change-safety` | CREATE | 3 | 5 | 4 | 5 | 4 | 2 | **19** |
| `openai-compat-contract-guardian` | CREATE | 3 | 4 | 4 | 5 | 3 | 3 | **16** |
| `validation-gate-runner` | CREATE | 5 | 3 | 4 | 4 | 4 | 2 | **18** |
| `documentation-writeback` | ADAPT (from `gsd-docs-update` concept) / CREATE | 4 | 3 | 3 | 4 | 4 | 2 | **16** |
| `deployment-readiness-auditor` | CREATE | 2 | 4 | 3 | 4 | 3 | 3 | **13** |
| ~~`frontend-backend-contract-checker`~~ | DO NOT CREATE | 2 | 2 | 2 | 3 | 3 | 3 | 7 — overlaps `openai-compat-contract-guardian`; too thin standalone |
| ~~`legacy-isolation-guard`~~ | KEEP IN CLAUDE.md | 3 | 3 | 2 | 4 | 4 | 1 | n/a — one-line rule, not a workflow |

---

## 5. Recommended Initial Skill Set

Implementation order (5 skills):

1. **`capture-credentials-safety`** (primary) — highest risk × frequency.
2. **`validation-gate-runner`** — enforces `CLAUDE.md` §14 every change; unblocks safe releases.
3. **`sqlite-schema-change-safety`** — guards the inline, framework-free schema.
4. **`openai-compat-contract-guardian`** — guards the public `/v1` contract + documented gaps.
5. **`documentation-writeback`** — enforces `CLAUDE.md` §15 + README snapshot truthfulness.

`deployment-readiness-auditor` is **Phase 3 / optional** — the deployment
report already exists at `docs/deployment/`; the skill generalizes it but is
lower frequency.

---

## 6. Detailed Skill Specifications

### 6.1 `capture-credentials-safety`

- **Decision:** CREATE
- **Problem solved:** Account captures are live ChatGPT credentials. Add /
  update / verify / rotate flows touch encryption (`crypto.py`), the
  `secrets/accounts/` tree, `.gitignore`/`.dockerignore`, and redacted
  logging. Agents leak captures by pasting them into logs, committing them,
  or running the wrong crypto mode.
- **Trigger conditions:** Any task that adds, updates, verifies, deletes, or
  rotates a ChatGPT account capture; any edit to `crypto.py`,
  `request_capture.py`, `auth.py`, or the `secrets/accounts/` layout; any CLI
  change to `account add/update/verify/delete` or `secrets rotate`.
- **Inputs:** the capture operation type; the target alias; the crypto mode
  (auto key file vs `CHATGPT_SECRETS_PASSPHRASE` vs `--secrets-passphrase-prompt`).
- **Required reading:** `CLAUDE.md` §16, `docs/ACCOUNT_CAPTURE.md`,
  `chatgpt_api/providers/chatgpt/crypto.py`, `chatgpt_api/providers/chatgpt/request_capture.py`,
  `.gitignore`, `.dockerignore`.
- **Procedure:**
  1. Confirm the operation is authorized and the alias is an ASCII slug.
  2. Verify the capture path stays under `secrets/accounts/<alias>/` and is
     covered by both ignore files (`git check-ignore`).
  3. Confirm crypto mode: never write a passphrase to disk; flag
     `CHATGPT_SECRETS_PASSPHRASE` env exposure as a risk for headless Docker.
  4. For rotate: confirm re-encryption of every capture before deleting the
     old key file; warn that legacy plaintext captures are read transparently.
  5. Assert no code path logs raw `Authorization`, cookies, sentinel/proof
     tokens, or capture contents — only redacted summaries.
  6. Run the capture/crypto tests (`tests/test_crypto.py`,
     `tests/test_request_capture.py`, `tests/test_chatgpt_auth.py`).
- **Outputs:** a short safety checklist response (pass/fail per step) + the
  exact test commands run + their results.
- **Validation:** `git check-ignore` returns the capture path; the named test
  files pass; a grep of the touched code for forbidden log tokens returns
  nothing.
- **Safety constraints:** never print a capture, cookie, bearer, or passphrase
  value; never commit `secrets/`; never disable encryption; never auto-rotate
  without confirmation.
- **Existing skill candidate:** `gsd-secure-phase` / built-in `security-review`
  overlap generically but do not encode these rules — **adaptation would
  approximate a rewrite**, so CREATE.
- **Value scores:** F5 R5 T4 S5 V4 M2 → **Priority 21**.
- **Maintenance notes:** update when `crypto.py` key modes change, when the
  capture directory layout changes, or when `CLAUDE.md` §16 is revised.

### 6.2 `validation-gate-runner`

- **Decision:** CREATE
- **Problem solved:** `CLAUDE.md` §14 maps change types → commands, but agents
  run the wrong subset, skip the frontend `bun` gates, or mis-report the
  Windows `0o600` test failure as a code defect.
- **Trigger conditions:** Before declaring any backend, API, schema, auth,
  routing, frontend, or docs change complete.
- **Inputs:** the change type(s) touched (backend-only / API route / schema /
  auth-secrets / routing-transport / console / game / docker / docs-only).
- **Required reading:** `CLAUDE.md` §14, §17 (Windows caveat), `pyproject.toml`,
  `apps/bridge-console/package.json`, `apps/character-game/package.json`.
- **Procedure:**
  1. Map the change type to the §14 command set.
  2. Run `python -m compileall chatgpt_api` always (backend).
  3. Run `python -m pytest -q`; if the only failure is
     `test_load_secrets_key_creates_owner_only_key_file` on Windows, classify
     it as the documented platform mismatch (§17), **not** a code defect — do
     not "fix" it.
  4. For frontend changes, run the matching `bun run --cwd … check` / `build`
     / `test`; report NOT AVAILABLE if `bun` is absent (do not fabricate).
  5. For docker changes, run `docker compose config --quiet` (non-destructive)
     and note that `docker compose up --build` is a deploy action requiring
     authorization.
  6. For API changes, run the chat smoke against a running server only if a
     capture exists; otherwise mark BLOCKED.
- **Outputs:** a per-command table (command / WD / result / meaning) matching
  the §14 format.
- **Validation:** every required command has an explicit PASS/FAIL/BLOCKED/NOT
  AVAILABLE row; no row is blank.
- **Safety constraints:** never run `docker compose up` (deploy action), never
  reset/reseed a DB, never run a destructive pytest; never mark BLOCKED as
  PASS.
- **Existing skill candidate:** `gsd-add-tests` / `verify` / `run` overlap as
  primitives but are not change-type-gated to §14 → CREATE.
- **Value scores:** F5 R3 T4 S4 V4 M2 → **Priority 18**.
- **Maintenance notes:** update when §14 or package scripts change.

### 6.3 `sqlite-schema-change-safety`

- **Decision:** CREATE
- **Problem solved:** The admin schema is inline in `BridgeAdminStore._migrate`
  with no migration framework, no down-migration, and an idempotency +
  parameterized-query requirement. Easy to add a non-idempotent statement or
  forget that operation records are in-memory only.
- **Trigger conditions:** Any edit to `chatgpt_api/api/admin_store.py`
  `_migrate()`, or any code adding a table/column/index to the bridge DB.
- **Inputs:** the diff to `admin_store.py`; the new table/column/index.
- **Required reading:** `CLAUDE.md` §11, `chatgpt_api/api/admin_store.py`
  (especially `_migrate` and the parameterized-query call sites).
- **Procedure:**
  1. Confirm every new DDL uses `CREATE TABLE/INDEX IF NOT EXISTS` (idempotent).
  2. Confirm no destructive `DROP`/`ALTER` that would break an existing DB on
     upgrade.
  3. Confirm all new queries use parameter placeholders (`?`), never f-string
     SQL with user data.
  4. Confirm the change is forward-compatible (older code on newer schema still
     works) since there is no down-migration.
  5. Confirm operation records are still treated as in-memory (not persisted)
     unless explicitly intended.
  6. Run `python -m pytest tests/test_admin_store.py -q`.
- **Outputs:** a checklist + the admin_store test result.
- **Validation:** `tests/test_admin_store.py` passes; a grep for f-string SQL
  on user data in the touched region returns nothing.
- **Safety constraints:** never generate a destructive migration; never claim
  a migration is reversible (no down-migration exists — verified).
- **Existing skill candidate:** none specific; `gsd-nyquist-auditor` is
  generic → CREATE.
- **Value scores:** F3 R5 T4 S5 V4 M2 → **Priority 19**.
- **Maintenance notes:** update if a migration framework is ever introduced
  (currently explicitly none).

### 6.4 `openai-compat-contract-guardian`

- **Decision:** CREATE
- **Problem solved:** The `/v1` API is "OpenAI-shaped" with **documented
  contract gaps** (`CLAUDE.md` §12: zero token usage, `n=1` images, JSON image
  refs for edits, prompt-bridged tool calls). Agents "fix" these silently,
  break backward compatibility, or change a route shape without updating the
  contract doc.
- **Trigger conditions:** Any edit to a `/v1` route handler, response shape,
  model alias, or error normalization in `openai_compat.py`; or any edit to
  `docs/OPENAI_COMPATIBILITY.md`.
- **Inputs:** the route/response/alias changed; the handler diff.
- **Required reading:** `CLAUDE.md` §12, `docs/OPENAI_COMPATIBILITY.md`, the
  affected handler region of `chatgpt_api/api/openai_compat.py`.
- **Procedure:**
  1. Identify the affected public route and response shape.
  2. Check the change against `docs/OPENAI_COMPATIBILITY.md`; if the doc and
     code diverge, report the conflict explicitly (do not silently pick one).
  3. Verify no documented gap was silently "fixed" (zero token usage, `n=1`,
     JSON image refs, prompt-bridged tools) unless the task explicitly
     changes it.
  4. Verify backward compatibility for public route shapes and CLI command
     names.
  5. Verify error objects stay OpenAI-shaped with normalized `code`s.
  6. Run `tests/test_openai_compat.py`.
- **Outputs:** a contract-impact note (affected route, doc updated? gap
  touched? backward-compat? ) + test result.
- **Validation:** `tests/test_openai_compat.py` passes; `OPENAI_COMPATIBILITY.md`
  updated iff the public shape changed.
- **Safety constraints:** never silently change a public route shape; never
  remove a model alias without checking `GET /v1/models`; never claim a gap is
  "fixed."
- **Existing skill candidate:** `gsd-code-review` / built-in `code-review`
  overlap generically → CREATE (repo-specific contract knowledge required).
- **Value scores:** F3 R4 T4 S5 V3 M3 → **Priority 16**.
- **Maintenance notes:** update when routes, aliases, or `OPENAI_COMPATIBILITY.md`
  change.

### 6.5 `documentation-writeback`

- **Decision:** ADAPT (concept from `gsd-docs-update`) → effectively CREATE
- **Problem solved:** `CLAUDE.md` §15 specifies exactly which docs to update
  for which change and requires the README "Latest Validation Snapshot" to
  stay truthful. Agents update the wrong doc, skip the snapshot, or invent
  backlog files.
- **Trigger conditions:** When finishing a task that changes public behavior,
  config, env, schema, CLI, or module boundaries.
- **Inputs:** the changed surfaces (route / env / schema / CLI / module /
  docker).
- **Required reading:** `CLAUDE.md` §15, §4 (which docs exist), the affected
  `docs/*.md`, `README.md` snapshot section.
- **Procedure:**
  1. Map changed surfaces → required doc updates per §15 table.
  2. Update only the affected docs; never create `CURRENT_STATE.md` /
     `ACTIVE_TASKS.md` / `IMPLEMENT_LOG.md` / `ROADMAP.md` (forbidden, §4/§15).
  3. If public behavior changed, re-run the §14 gates and update the README
     snapshot date + results truthfully; mark BLOCKED checks honestly.
  4. Keep `docs/DOCKER.md` and `.env.example` in sync for env changes.
  5. Leave `references/legacy/` clearly marked legacy.
- **Outputs:** a write-back summary (doc → change applied) + the updated
  snapshot claim.
- **Validation:** every changed surface has a corresponding doc-update row;
  no forbidden backlog file was created; the snapshot claim matches actually
  run commands.
- **Safety constraints:** never overwrite historical records; never bump the
  snapshot date without re-running the checks; never claim a check passed that
  was not run.
- **Existing skill candidate:** `gsd-docs-update` — closest fit but assumes
  GSD planning artifacts this repo lacks → adapt/CREATE.
- **Value scores:** F4 R3 T3 S4 V4 M2 → **Priority 16**.
- **Maintenance notes:** update when §15 doc list changes.

---

## 7. Download Versus Create Decision

| Skill | Decision | Rationale |
| --- | --- | --- |
| `capture-credentials-safety` | **CREATE** | Repo-specific credential/crypto/logging rules; no installed/public skill encodes them; trust risk forbids download. |
| `validation-gate-runner` | **CREATE** | Tied to `CLAUDE.md` §14 matrix + Windows caveat; no match. |
| `sqlite-schema-change-safety` | **CREATE** | Inline, framework-free schema idempotency is unique here. |
| `openai-compat-contract-guardian` | **CREATE** | OpenAI-shaped contract + documented gaps are repo-specific. |
| `documentation-writeback` | **ADAPT → CREATE** | Concept overlaps `gsd-docs-update`, but GSD lifecycle assumptions don't apply; effectively a new skill. |
| `deployment-readiness-auditor` (Phase 3) | **CREATE** | Generalizes the existing deployment report; low frequency. |
| Rules like "legacy is not runtime", "mock/local-dev-key is dev-only", "ops records in-memory", "token usage is zero" | **KEEP IN CLAUDE.md** | One-line always-on rules; turning into skills adds indirection. |

**Overall: create project-specific skills.** A hybrid would only use the
built-in `code-review`/`security-review`/`verify`/`run` as *primitives* that
the new skills call — not as substitutes.

---

## 8. Recommended Skill Directory

Claude Code repository-local skills convention: `.claude/skills/<skill>/SKILL.md`
(+ optional `references/`, `templates/`). This repo currently has no `.claude/`
directory, so it would be created. Proposed structure (skills **reference**
authoritative docs rather than copy them):

```text
.claude/
└── skills/
    ├── capture-credentials-safety/
    │   └── SKILL.md            # references CLAUDE.md §16, docs/ACCOUNT_CAPTURE.md, crypto.py
    ├── validation-gate-runner/
    │   └── SKILL.md            # references CLAUDE.md §14, §17
    ├── sqlite-schema-change-safety/
    │   └── SKILL.md            # references admin_store.py:_migrate
    ├── openai-compat-contract-guardian/
    │   └── SKILL.md            # references docs/OPENAI_COMPATIBILITY.md
    └── documentation-writeback/
        └── SKILL.md            # references CLAUDE.md §15
```

Each skill: **only `SKILL.md`** initially. Add `references/` (e.g., a
capture-redaction grep checklist) or `templates/` only if a skill needs
boilerplate the repo does not already contain. **Do not** copy whole docs into
skill folders — point at the authoritative file.

---

## 9. Implementation Roadmap

### Phase 1 — one highest-value skill

- **`capture-credentials-safety`**
- **Acceptance:** invoking it on a sample capture add/update produces a
  pass/fail checklist, runs `test_crypto.py`/`test_request_capture.py`/
  `test_chatgpt_auth.py`, and `git check-ignore` confirms the capture path —
  without ever printing a credential.

### Phase 2 — next three skills

- `validation-gate-runner`, `sqlite-schema-change-safety`,
  `openai-compat-contract-guardian`.
- **Acceptance:** each maps its trigger to the correct `CLAUDE.md` section,
  runs the named tests, and returns a per-command PASS/FAIL/BLOCKED/NOT
  AVAILABLE table; the schema skill refuses to mark a migration reversible.

### Phase 3 — optional specialized skills

- `documentation-writeback` and (lower priority)
  `deployment-readiness-auditor` (generalizes
  `docs/deployment/DEPLOYMENT_READINESS_AND_RUNBOOK.md`).
- **Acceptance:** writeback skill updates exactly the §15-mapped docs and
  refuses to create forbidden backlog files; deployment auditor reproduces the
  readiness verdict from verified commands only.

---

## 10. Risks and Maintenance

- **Stale skill instructions:** skills reference `CLAUDE.md` sections and
  inline schema — when those move, skills break silently. Mitigation: skills
  cite section numbers + file paths and re-read them at runtime; a periodic
  grep audit that section paths still resolve.
- **Duplicated governance:** risk that a skill restates `CLAUDE.md` and the
  two drift. Mitigation: skills **reference**, never copy, the authoritative
  doc; `CLAUDE.md` remains the single source.
- **Unsafe third-party skills:** this repo handles live credentials; never
  DOWNLOAD a skill touching capture/crypto/auth. CREATE-only for that path.
- **Version compatibility:** skills must use the current Claude Code
  `.claude/skills/<name>/SKILL.md` convention; verify against the running
  environment when implementing.
- **Excessive context size:** keep each `SKILL.md` concise and pointer-based;
  do not inline the 5,580-line handler or full docs.
- **Over-automation:** skills must **not** auto-run `docker compose up`,
  auto-rotate captures, or auto-delete artifacts — they produce checklists and
  run only non-destructive commands; destructive steps require confirmation.
- **Required ownership:** whoever maintains `CLAUDE.md` maintains these skills
  in lockstep.

---

## 11. Recommended Next Action

**Create the first repository-local skill: `capture-credentials-safety`
(`.claude/skills/capture-credentials-safety/SKILL.md`)** — then validate it by
running it against a throwaway capture-add dry run (no real credentials) and
confirming the safety checklist + `git check-ignore` + the three crypto/auth
test files behave as specified.

Do not implement it in this task.

---

## 12. Implementation Status — `capture-credentials-safety`

> Updated 2026-06-27 after the Phase 1 skill was created and validated.
> This section records implementation status only; the analysis in §1–§11 is
> unchanged.

- **Status:** `capture-credentials-safety` **created and validated.**
- **Actual path:** `.claude/skills/capture-credentials-safety/SKILL.md`
  (Claude Code repo-local convention; verified against installed
  `gsd-docs-update` and `gsd-code-review` skills, which use the same
  `name` / `description` / `allowed-tools` YAML frontmatter in
  `~/.claude/skills/<name>/SKILL.md`).
- **Discovery validation:** the skill is recognized by the running Claude
  Code environment — it now appears in the session's available-skills list as
  `capture-credentials-safety`. Frontmatter parses as valid YAML after the
  `description` was quoted (initial unquoted form broke on a colon; installed
  skills quote theirs, so the format was corrected to match).
- **Dry-run result (synthetic, no real credential, no external contact):**
  - Encryption: stored content begins with `enc:v1:`; `is_encrypted=True`;
    synthetic secret string **not** present in the ciphertext file.
  - Redaction: `CapturedRequest.redacted_headers()` returned `<redacted>` for
    both `authorization` and `cookie`; secret value not present in redacted
    output.
  - Git: `git check-ignore -v secrets/accounts/synthetic-dryrun/chatgpt-request.txt`
    → matched by `.gitignore:27` (`secrets/`), exit 0.
  - Cleanup: temp directory removed; `git status` shows only intended paths
    (`.claude/`, `docs/deployment/`, `docs/reports/`) — no stray capture files.
- **Test results (repo root):**
  - `python -m pytest tests/test_crypto.py -q` → **11 passed, 1 failed**.
    The single failure is the documented Windows `0o600` platform mismatch
    (`438 == 0o666` vs `384 == 0o600`, `CLAUDE.md` §17) — pre-existing, not a
    code defect, not caused by the skill. Do not "fix" by relaxing the
    `os.open(..., 0o600)` permission.
  - `python -m pytest tests/test_request_capture.py -q` → **9 passed**.
  - `python -m pytest tests/test_chatgpt_auth.py -q` → **3 passed**.
- **Unresolved limitations:**
  - `bun` is not installed locally; no frontend checks apply to this skill.
  - No live ChatGPT capture exists, so end-to-end provider flows were not
    exercised (and intentionally must not be with real credentials).
  - Skill discovery was validated by the session listing + YAML parse; there
    is no dedicated skill-registry CLI in this environment to query further.
- **Next recommended skill:** `sqlite-schema-change-safety` (Phase 2) —
  guards the inline, framework-free `_migrate()` schema in `admin_store.py`.
