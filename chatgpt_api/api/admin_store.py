"""Small SQLite metadata store for the local bridge admin console."""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


class BridgeAdminStore:
    def __init__(self, path: Path) -> None:
        self.path = path.expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._migrate()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def _migrate(self) -> None:
        with self._connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS artifacts (
                    file_id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    filename TEXT NOT NULL,
                    path TEXT NOT NULL,
                    download_url TEXT NOT NULL,
                    content_type TEXT NOT NULL,
                    bytes INTEGER,
                    account TEXT,
                    prompt TEXT,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS artifacts_created_idx
                    ON artifacts(created_at DESC);

                CREATE TABLE IF NOT EXISTS account_captures (
                    account TEXT PRIMARY KEY,
                    capture_path TEXT NOT NULL,
                    plan_type TEXT,
                    email_masked TEXT,
                    capabilities_json TEXT NOT NULL DEFAULT '{}',
                    checks_json TEXT NOT NULL DEFAULT '[]',
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                -- Phase 1A: durable Agent Job persistence. Additive only;
                -- see docs/agent_bridge/DATA_MODEL.md. No foreign-key
                -- constraints are declared, matching the existing schema
                -- style (artifacts/account_captures have no FKs either).
                CREATE TABLE IF NOT EXISTS agent_jobs (
                    job_id TEXT PRIMARY KEY,
                    client_request_id TEXT,
                    idempotency_key TEXT,
                    request_hash TEXT,
                    request_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    priority INTEGER NOT NULL DEFAULT 0,
                    model TEXT NOT NULL,
                    account_alias TEXT,
                    request_storage_key TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    queued_at TEXT,
                    started_at TEXT,
                    completed_at TEXT,
                    cancel_requested_at TEXT,
                    cancelled_at TEXT,
                    expires_at TEXT,
                    attempt_count INTEGER NOT NULL DEFAULT 0,
                    max_attempts INTEGER NOT NULL,
                    error_code TEXT,
                    error_message TEXT,
                    result_id TEXT,
                    callback_url TEXT,
                    callback_status TEXT,
                    lease_owner TEXT,
                    lease_expires_at TEXT,
                    next_retry_at TEXT
                );

                CREATE INDEX IF NOT EXISTS agent_jobs_status_idx
                    ON agent_jobs(status);
                CREATE INDEX IF NOT EXISTS agent_jobs_created_idx
                    ON agent_jobs(created_at DESC);
                CREATE INDEX IF NOT EXISTS agent_jobs_client_idx
                    ON agent_jobs(client_request_id);
                -- Partial unique index: one active job per non-null
                -- idempotency key. This is the final race-safety mechanism
                -- for concurrent same-key submissions.
                CREATE UNIQUE INDEX IF NOT EXISTS agent_jobs_idem_idx
                    ON agent_jobs(idempotency_key)
                    WHERE idempotency_key IS NOT NULL;

                CREATE TABLE IF NOT EXISTS job_results (
                    result_id TEXT PRIMARY KEY,
                    job_id TEXT NOT NULL UNIQUE,
                    result_type TEXT NOT NULL,
                    text_content TEXT,
                    response_storage_key TEXT,
                    model TEXT,
                    account_alias TEXT,
                    finish_reason TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS job_events (
                    event_id TEXT PRIMARY KEY,
                    job_id TEXT NOT NULL,
                    sequence_no INTEGER NOT NULL,
                    event_type TEXT NOT NULL,
                    event_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE UNIQUE INDEX IF NOT EXISTS job_events_job_seq_idx
                    ON job_events(job_id, sequence_no);
                CREATE INDEX IF NOT EXISTS job_events_job_idx
                    ON job_events(job_id, sequence_no);

                CREATE TABLE IF NOT EXISTS job_attempts (
                    attempt_id TEXT PRIMARY KEY,
                    job_id TEXT NOT NULL,
                    attempt_no INTEGER NOT NULL,
                    account_alias TEXT,
                    provider TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    completed_at TEXT,
                    status TEXT NOT NULL,
                    error_code TEXT,
                    error_message TEXT
                );

                CREATE UNIQUE INDEX IF NOT EXISTS job_attempts_job_no_idx
                    ON job_attempts(job_id, attempt_no);
                CREATE INDEX IF NOT EXISTS job_attempts_job_idx
                    ON job_attempts(job_id, attempt_no);
                """
            )
            # CREATE TABLE IF NOT EXISTS cannot add a column to an existing
            # table, so add artifacts.job_id idempotently via introspection.
            # Never destroys or rewrites existing rows.
            existing_columns = {row["name"] for row in db.execute("PRAGMA table_info(artifacts)").fetchall()}
            if "job_id" not in existing_columns:
                db.execute("ALTER TABLE artifacts ADD COLUMN job_id TEXT")
            db.execute(
                "CREATE INDEX IF NOT EXISTS artifacts_job_idx ON artifacts(job_id)"
            )
            # Phase 1C.1: add agent_jobs.next_retry_at idempotently for
            # databases created under Phase 1A (which lack the column). The
            # retry index is created after this ALTER so the column exists in
            # both fresh and legacy databases.
            agent_columns = {row["name"] for row in db.execute("PRAGMA table_info(agent_jobs)").fetchall()}
            if "next_retry_at" not in agent_columns:
                db.execute("ALTER TABLE agent_jobs ADD COLUMN next_retry_at TEXT")
            db.execute(
                "CREATE INDEX IF NOT EXISTS agent_jobs_retry_idx ON agent_jobs(status, next_retry_at)"
            )

    def record_artifact(
        self,
        asset: dict[str, Any],
        *,
        kind: str,
        account: str | None = None,
        prompt: str | None = None,
        metadata: dict[str, Any] | None = None,
        job_id: str | None = None,
    ) -> None:
        with self._connect() as db:
            db.execute(
                """
                INSERT OR REPLACE INTO artifacts (
                    file_id, kind, filename, path, download_url, content_type, bytes,
                    account, prompt, metadata_json, created_at, job_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, COALESCE(
                    (SELECT created_at FROM artifacts WHERE file_id = ?),
                    ?
                ), ?)
                """,
                (
                    str(asset.get("id") or ""),
                    kind,
                    str(asset.get("filename") or "download"),
                    str(asset.get("path") or ""),
                    str(asset.get("download_url") or ""),
                    str(asset.get("content_type") or "application/octet-stream"),
                    asset.get("bytes") if isinstance(asset.get("bytes"), int) else None,
                    account,
                    prompt,
                    json.dumps(metadata or {}, ensure_ascii=False, sort_keys=True),
                    str(asset.get("id") or ""),
                    utc_now(),
                    job_id,
                ),
            )

    def list_artifacts(self, *, limit: int = 100) -> list[dict[str, Any]]:
        safe_limit = max(1, min(int(limit), 500))
        with self._connect() as db:
            rows = db.execute(
                "SELECT * FROM artifacts ORDER BY created_at DESC LIMIT ?",
                (safe_limit * 4,),
            ).fetchall()
        artifacts = [self._artifact_row(row) for row in rows]
        stale_ids = [artifact["file_id"] for artifact in artifacts if not artifact["exists"]]
        if stale_ids:
            self.delete_artifacts(stale_ids)
        return [artifact for artifact in artifacts if artifact["exists"]][:safe_limit]

    def get_artifact(self, file_id: str) -> dict[str, Any] | None:
        with self._connect() as db:
            row = db.execute("SELECT * FROM artifacts WHERE file_id = ?", (file_id,)).fetchone()
        return self._artifact_row(row) if row is not None else None

    def list_artifacts_by_job(self, job_id: str, *, limit: int = 100) -> list[dict[str, Any]]:
        """List artifacts associated with an AgentJob (Phase 1A).

        Rows with ``job_id IS NULL`` (legacy synchronous-flow artifacts) are
        not returned. Missing files are pruned, matching ``list_artifacts``.
        """

        safe_limit = max(1, min(int(limit), 500))
        with self._connect() as db:
            rows = db.execute(
                "SELECT * FROM artifacts WHERE job_id = ? ORDER BY created_at DESC LIMIT ?",
                (job_id, safe_limit * 4),
            ).fetchall()
        artifacts = [self._artifact_row(row) for row in rows]
        stale_ids = [artifact["file_id"] for artifact in artifacts if not artifact["exists"]]
        if stale_ids:
            self.delete_artifacts(stale_ids)
        return [artifact for artifact in artifacts if artifact["exists"]][:safe_limit]

    def artifact_count(self) -> int:
        with self._connect() as db:
            rows = db.execute("SELECT file_id, path FROM artifacts").fetchall()
        stale_ids = [row["file_id"] for row in rows if not Path(row["path"]).is_file()]
        if stale_ids:
            self.delete_artifacts(stale_ids)
        return len(rows) - len(stale_ids)

    def delete_artifact(self, file_id: str) -> dict[str, Any] | None:
        with self._connect() as db:
            row = db.execute("SELECT * FROM artifacts WHERE file_id = ?", (file_id,)).fetchone()
            if row is None:
                return None
            artifact = self._artifact_row(row)
            db.execute("DELETE FROM artifacts WHERE file_id = ?", (file_id,))
        return artifact

    def delete_artifacts(self, file_ids: list[str]) -> int:
        safe_ids = [file_id for file_id in file_ids if file_id]
        if not safe_ids:
            return 0
        placeholders = ",".join("?" for _ in safe_ids)
        with self._connect() as db:
            cursor = db.execute(f"DELETE FROM artifacts WHERE file_id IN ({placeholders})", safe_ids)
            return cursor.rowcount

    def record_account_capture(
        self,
        *,
        account: str,
        capture_path: Path,
        inspection: dict[str, Any],
    ) -> None:
        detected = inspection.get("detected") if isinstance(inspection.get("detected"), dict) else {}
        with self._connect() as db:
            db.execute(
                """
                INSERT OR REPLACE INTO account_captures (
                    account, capture_path, plan_type, email_masked,
                    capabilities_json, checks_json, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    account,
                    str(capture_path),
                    detected.get("plan_type"),
                    detected.get("email"),
                    json.dumps(inspection.get("capabilities") or {}, ensure_ascii=False, sort_keys=True),
                    json.dumps(inspection.get("checks") or [], ensure_ascii=False, sort_keys=True),
                    utc_now(),
                ),
            )

    def list_account_captures(self) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute("SELECT * FROM account_captures ORDER BY account ASC").fetchall()
        return [self._account_row(row) for row in rows]

    def delete_account_capture(self, account: str) -> bool:
        with self._connect() as db:
            cursor = db.execute("DELETE FROM account_captures WHERE account = ?", (account,))
            return cursor.rowcount > 0

    def get_setting(self, key: str, default: Any = None) -> Any:
        with self._connect() as db:
            row = db.execute("SELECT value_json FROM settings WHERE key = ?", (key,)).fetchone()
        if row is None:
            return default
        try:
            return json.loads(row["value_json"])
        except json.JSONDecodeError:
            return default

    def set_setting(self, key: str, value: Any) -> None:
        with self._connect() as db:
            db.execute(
                """
                INSERT OR REPLACE INTO settings (key, value_json, updated_at)
                VALUES (?, ?, ?)
                """,
                (key, json.dumps(value, ensure_ascii=False, sort_keys=True), utc_now()),
            )

    def delete_setting(self, key: str) -> bool:
        with self._connect() as db:
            cursor = db.execute("DELETE FROM settings WHERE key = ?", (key,))
            return cursor.rowcount > 0

    def _artifact_row(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "file_id": row["file_id"],
            "kind": row["kind"],
            "filename": row["filename"],
            "path": row["path"],
            "download_url": row["download_url"],
            "content_type": row["content_type"],
            "bytes": row["bytes"],
            "account": row["account"],
            "prompt": row["prompt"],
            "metadata": _json_or_empty(row["metadata_json"]),
            "created_at": row["created_at"],
            "job_id": row["job_id"],
            "exists": Path(row["path"]).is_file(),
        }

    def _account_row(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "account": row["account"],
            "capture_path": row["capture_path"],
            "plan_type": row["plan_type"],
            "email": row["email_masked"],
            "capabilities": _json_or_empty(row["capabilities_json"]),
            "checks": _json_or_empty(row["checks_json"]),
            "updated_at": row["updated_at"],
        }


def _json_or_empty(value: str | None) -> Any:
    if not value:
        return {}
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return {}
