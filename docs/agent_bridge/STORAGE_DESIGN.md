# Storage Design — AI Agent → ChatGPT API Bridge

> Phase 1: SQLite (metadata) + local filesystem (binaries/large text). No
> new infrastructure. Grounded in current conventions
> (`outputs/chatgpt-images/`, `outputs/chatgpt-research/`,
  `artifacts` table).

## 1. Local layout (Phase 1)

```text
outputs/
  agent-jobs/
    <job_id>/
      request.json          # canonical request payload
      inputs/               # uploaded source images (Phase 2)
        <input_id>.<ext>
      results/
        response.json       # large normalized response (Phase 1)
      artifacts/            # symlink/copy reference into existing image/research stores
  chatgpt-images/           # (existing) generated + edited images
  chatgpt-research/         # (existing) Deep Research markdown
  chatgpt-admin.sqlite      # (existing) metadata
```

- Generated images/research reports continue to land in the **existing**
  `chatgpt-images/` / `chatgpt-research/` stores and are registered in the
  existing `artifacts` table (with the new nullable `job_id` column). This
  avoids duplicating the artifact ownership and keeps the existing download
  path working.
- `outputs/agent-jobs/<job_id>/` holds job-specific request JSON, uploaded
  inputs (Phase 2), and large response JSON.

## 2. Metadata vs file ownership

| Data | Store | Why |
| --- | --- | --- |
| Job/attempt/event/result rows | SQLite | small, indexed, transactional |
| Request JSON | file (large/multimodal) + path in SQLite | avoid bloating SQLite |
| Response JSON | file + path in SQLite | can be large (research/chat) |
| Uploaded source images | file + `sha256` in SQLite | binary |
| Generated images / research | existing file stores + `artifacts` table | reuse |
| `download_url` | SQLite (`artifacts.download_url`) | built from `public_base_url` |

**SQLite is the metadata source of truth; the filesystem is the binary/large-
text store.** A metadata row with a missing file is a reconcile target.

## 3. Atomic file writes

- Write to `<name>.tmp.<pid>` then `os.replace()` to the final path
  (atomic on POSIX; on Windows `os.replace` is atomic for same-volume
  renames). The current capture save uses plain `write_text` (not atomic —
  noted as a finding in the prior skill audit); the agent-job layer should
  use temp+rename.
- Temporary files use `<filename>.tmp.<pid>` and are cleaned up on failure.

## 4. Hashing / MIME validation

- `sha256` of every uploaded input and every generated artifact, stored in
  SQLite. Verified on read for inputs; recorded for artifacts.
- MIME allowlist for image inputs: `image/png`, `image/jpeg`,
  `image/webp`, `image/gif`. Reject others with 400.
- Magic-byte sniff in addition to declared MIME (proposed) — do not trust
  the `Content-Type` alone.

## 5. Limits (proposed; enforced at the API layer)

- Max request body: 25 MiB.
- Max image size: 20 MiB each.
- Max images per request: 10 (existing).
- Max output size: bounded by provider; research reports capped at disk
  quota guard.
- Max `messages`/text length: configurable; default generous for chat.

## 6. Cleanup / retention

- Default retention: 7 days after terminal state (`succeeded`/`failed`/
  `cancelled`/`expired`), configurable via `settings`.
- Cleanup sweep: deletes `agent_jobs` rows past retention + their
  `outputs/agent-jobs/<job_id>/` directory + associated artifact files (for
  job-owned artifacts only; never delete artifacts owned by the legacy
  synchronous flow unless they have a `job_id`).
- Orphan-file reconciliation: scan `outputs/agent-jobs/` for directories
  with no `agent_jobs` row → move to a quarantine dir or delete.
- Missing-file reconciliation: `job_inputs`/`artifacts` rows whose file is
  missing → mark `result_type=error` or prune the row (existing
  `list_artifacts` already prunes stale artifact rows).

## 7. Backup / restore

- Backup = tarball of `outputs/` (SQLite + files) — operator-manual (no
  automation in repo). Restore = unpack + restart.
- SQLite can be backed up live via `VACUUM INTO` (proposed) for a
  consistent snapshot without stopping the server.

## 8. Security

- Path traversal prevention: `file_id`/`job_id`/`input_id` are opaque
  server-generated IDs; filesystem paths are derived from these IDs, never
  from client input. Reject any client-supplied path containing `..` or
  absolute separators.
- Download filename: the stored `filename` from `artifacts`, not the URL.
- Artifact authorization: same shared-key gate as today (Phase 1 limitation —
  see `SECURITY_MODEL.md`).
- Disk-full behavior: write failures → job `failed` with
  `error_code=storage_failure`; no partial success.

## 9. Future storage interface (not implemented)

```python
class ArtifactStorage(Protocol):
    def put(self, key: str, data: bytes, *, mime_type: str) -> str: ...
    def get(self, key: str) -> bytes: ...
    def delete(self, key: str) -> bool: ...
    def exists(self, key: str) -> bool: ...
    def metadata(self, key: str) -> dict: ...  # size, sha256, mime_type
```

- `LocalArtifactStorage` (Phase 1) — wraps `outputs/`.
- `S3ArtifactStorage` (Phase 4) — MinIO / AWS S3 / Cloudflare R2.

## 10. Why Redis is (or is not) appropriate

- **Not appropriate** as the authoritative binary/artifact store — binaries
  stay on disk/S3.
- **Possibly appropriate later** for: transient lease coordination across
  multiple API/worker processes, rate-limit counters, and a lightweight
  queue pointer — **only when** multiple worker nodes exist. Phase 1 uses
  SQLite for all of these (single process).

## 11. Migration thresholds (objective)

Add a component **only when** the matching trigger is met:

| Component | Trigger |
| --- | --- |
| MinIO / S3-compatible | multiple API instances needing shared artifact access **or** artifact volume > ~50 GiB **or** cross-host access |
| Redis | multiple worker nodes needing shared leases/queue **or** queue throughput > ~50 jobs/min sustained |
| PostgreSQL | relational scale, distributed coordination, reporting joins, or multi-tenant ownership that SQLite cannot serve **or** concurrent writers causing lock contention |
| Separate worker containers | long-running Deep Research jobs blocking the API process **or** >1 worker node needed for capacity |
| Kubernetes | multi-node HA + autoscaling requirements |

Below these thresholds, SQLite + local files + in-process coordinator is the
correct, dependency-light choice aligned with the repo's philosophy
(`AGENTS.md` §10 — no new dependency without justification).
