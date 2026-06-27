"""Phase 1A durable AgentJob persistence and domain logic.

Ownership boundary for asynchronous agent jobs. This module contains the
state machine, idempotency, canonical request hashing, server-generated IDs,
redaction, and the repository operations that persist jobs, results, events,
and attempts to the SQLite admin database.

Scope (Phase 1A only):

- additive SQLite schema (in ``BridgeAdminStore._migrate``)
- durable job/result/event/attempt records
- state-machine validation with compare-and-swap transitions
- idempotent job creation backed by a partial unique index
- durable job claiming primitives + lease persistence
- stale-lease restart-recovery primitive
- durable cancellation-request state
- repository queries for status/events/attempts/results/artifacts

Explicitly NOT in this module (later phases):

- ``/v1/agent/*`` HTTP routes
- an execution coordinator thread / worker process
- provider calls (``ChatGPTProvider``, ``AccountRouter``, limiters)
- file upload parsing, image/multimodal inputs
- callbacks/webhooks, SSE streaming-delta persistence

Standard library only. One SQLite connection per operation. Parameterized
SQL exclusively. No ORM, no migration framework.
"""

from __future__ import annotations

import json
import re
import secrets
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from chatgpt_api.api.admin_store import BridgeAdminStore, utc_now

# --------------------------------------------------------------------------- #
# Status + state machine
# --------------------------------------------------------------------------- #

# Non-terminal lifecycle states.
STATUS_ACCEPTED = "accepted"
STATUS_VALIDATING = "validating"
STATUS_QUEUED = "queued"
STATUS_RUNNING = "running"
STATUS_STREAMING = "streaming"
STATUS_RETRY_WAIT = "retry_wait"
STATUS_CANCEL_REQUESTED = "cancel_requested"

# Terminal states: no transitions out.
STATUS_SUCCEEDED = "succeeded"
STATUS_FAILED = "failed"
STATUS_CANCELLED = "cancelled"
STATUS_EXPIRED = "expired"

TERMINAL_STATUSES = frozenset(
    {STATUS_SUCCEEDED, STATUS_FAILED, STATUS_CANCELLED, STATUS_EXPIRED}
)

ALL_STATUSES = TERMINAL_STATUSES | frozenset(
    {
        STATUS_ACCEPTED,
        STATUS_VALIDATING,
        STATUS_QUEUED,
        STATUS_RUNNING,
        STATUS_STREAMING,
        STATUS_RETRY_WAIT,
        STATUS_CANCEL_REQUESTED,
    }
)

# Explicit allowed transitions. Centrally defined; do not permit transitions
# out of terminal states.
ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    STATUS_ACCEPTED: frozenset({STATUS_VALIDATING}),
    STATUS_VALIDATING: frozenset({STATUS_QUEUED, STATUS_FAILED}),
    STATUS_QUEUED: frozenset({STATUS_RUNNING, STATUS_CANCEL_REQUESTED, STATUS_EXPIRED}),
    STATUS_RUNNING: frozenset(
        {STATUS_STREAMING, STATUS_RETRY_WAIT, STATUS_CANCEL_REQUESTED, STATUS_SUCCEEDED, STATUS_FAILED}
    ),
    STATUS_STREAMING: frozenset(
        {STATUS_RUNNING, STATUS_SUCCEEDED, STATUS_CANCEL_REQUESTED, STATUS_RETRY_WAIT}
    ),
    # streaming -> retry_wait is supported so a stream that fails with a
    # retryable error can back off and re-queue without an intermediate
    # running state. Documented in docs/agent_bridge/DATA_MODEL.md.
    STATUS_RETRY_WAIT: frozenset({STATUS_QUEUED, STATUS_CANCEL_REQUESTED, STATUS_EXPIRED}),
    STATUS_CANCEL_REQUESTED: frozenset({STATUS_CANCELLED}),
    STATUS_SUCCEEDED: frozenset(),
    STATUS_FAILED: frozenset(),
    STATUS_CANCELLED: frozenset(),
    STATUS_EXPIRED: frozenset(),
}

# Statuses from which a cancellation request may be persisted.
CANCELLABLE_STATUSES = frozenset(
    {STATUS_ACCEPTED, STATUS_VALIDATING, STATUS_QUEUED, STATUS_RUNNING, STATUS_STREAMING, STATUS_RETRY_WAIT}
)

# Statuses considered actively executing (lease renewal eligibility).
ACTIVE_EXECUTION_STATUSES = frozenset({STATUS_RUNNING, STATUS_STREAMING})

# --------------------------------------------------------------------------- #
# Errors
# --------------------------------------------------------------------------- #


class AgentJobError(Exception):
    """Base class for AgentJob domain errors."""


class InvalidTransition(AgentJobError):
    """Raised when a state transition is not allowed by the state machine."""


class JobNotFound(AgentJobError):
    """Raised when a job id does not match any persisted row."""


class IdempotencyConflict(AgentJobError):
    """Same idempotency key reused with a different request hash."""


class ClaimConflict(AgentJobError):
    """A job could not be claimed (missing, not queued, or race-lost)."""


# --------------------------------------------------------------------------- #
# Records (immutable, slots)
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class AgentJob:
    job_id: str
    request_type: str
    status: str
    model: str
    request_storage_key: str
    created_at: str
    max_attempts: int
    priority: int = 0
    client_request_id: str | None = None
    idempotency_key: str | None = None
    request_hash: str | None = None
    account_alias: str | None = None
    queued_at: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    cancel_requested_at: str | None = None
    cancelled_at: str | None = None
    expires_at: str | None = None
    attempt_count: int = 0
    error_code: str | None = None
    error_message: str | None = None
    result_id: str | None = None
    callback_url: str | None = None
    callback_status: str | None = None
    lease_owner: str | None = None
    lease_expires_at: str | None = None


@dataclass(frozen=True, slots=True)
class JobEvent:
    event_id: str
    job_id: str
    sequence_no: int
    event_type: str
    event_json: dict[str, Any]
    created_at: str


@dataclass(frozen=True, slots=True)
class JobAttempt:
    attempt_id: str
    job_id: str
    attempt_no: int
    provider: str
    started_at: str
    status: str
    account_alias: str | None = None
    completed_at: str | None = None
    error_code: str | None = None
    error_message: str | None = None


@dataclass(frozen=True, slots=True)
class JobResult:
    result_id: str
    job_id: str
    result_type: str
    created_at: str
    text_content: str | None = None
    response_storage_key: str | None = None
    model: str | None = None
    account_alias: str | None = None
    finish_reason: str | None = None


@dataclass(frozen=True, slots=True)
class JobCreateResult:
    """Result of ``create_job``. ``reused`` is True when an existing job was
    returned because the same idempotency key + request hash was submitted.
    Future HTTP code maps ``reused`` to 200 and a fresh creation to 201."""

    job: AgentJob
    reused: bool


@dataclass(frozen=True, slots=True)
class ClaimOutcome:
    job_id: str
    attempt_no: int


@dataclass(frozen=True, slots=True)
class RecoverySummary:
    requeued: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class JobListPage:
    jobs: list[AgentJob]
    next_cursor: str | None
    has_more: bool


# --------------------------------------------------------------------------- #
# ID + hash + redaction helpers
# --------------------------------------------------------------------------- #

_ID_PREFIX = {
    "job": "job_",
    "result": "result_",
    "event": "event_",
    "attempt": "attempt_",
}


def new_id(kind: str) -> str:
    """Opaque, collision-resistant server-generated id with a prefix.

    Uses ``secrets.token_hex`` (stdlib). Sortability is not required.
    """

    prefix = _ID_PREFIX.get(kind)
    if prefix is None:
        raise ValueError(f"unknown id kind: {kind!r}")
    return prefix + secrets.token_hex(12)


def canonical_request_hash(request: Any) -> str:
    """SHA-256 of canonical JSON for a request object.

    Stable across dictionary key order: keys are sorted, separators are
    fixed, UTF-8 encoded. Transport-only values are not stripped here; the
    caller is responsible for passing a semantically canonical request.
    """

    import hashlib

    canonical = json.dumps(request, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# Patterns whose values must never be persisted. We redact the value, not the
# whole message, so safe diagnostic text survives. Applies to error messages
# persisted on jobs/attempts.
_SECRET_VALUE_PATTERNS = (
    re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._\-+=]+"),
    re.compile(r"(?i)(authorization\s*:\s*)[^\r\n;]+"),
    re.compile(r"(?i)(cookie\s*:\s*)[^\r\n;]+"),
    re.compile(r"(?i)(set-cookie\s*:\s*)[^\r\n;]+"),
    re.compile(r"(?i)(api[_-]?key\s*[:=]\s*)[^\r\n;]+"),
    re.compile(r"(?i)(passphrase\s*[:=]\s*)[^\r\n;]+"),
    re.compile(r"(?i)(secret\s*[:=]\s*)[^\r\n;]+"),
    re.compile(r"(?i)(password\s*[:=]\s*)[^\r\n;]+"),
)

_MAX_ERROR_MESSAGE = 1000


def sanitize_error(message: Any, *, code: str | None = None) -> str:
    """Normalize an error message for safe persistence.

    - coerced to ``str`` and trimmed
    - secret-looking values (bearer tokens, cookies, api keys, passphrases)
      are replaced with ``<redacted>`` while leaving surrounding text intact
    - bounded in length
    """

    text = str(message).strip()
    if not text:
        return (code or "error").strip() or "error"
    for pattern in _SECRET_VALUE_PATTERNS:
        text = pattern.sub(lambda m: m.group(1) + "<redacted>", text)
    if len(text) > _MAX_ERROR_MESSAGE:
        text = text[:_MAX_ERROR_MESSAGE]
    return text


def validate_transition(current: str, target: str) -> None:
    """Raise ``InvalidTransition`` unless ``current -> target`` is allowed."""

    if current not in ALL_STATUSES:
        raise InvalidTransition(f"unknown current status: {current!r}")
    if current in TERMINAL_STATUSES:
        raise InvalidTransition(f"cannot transition from terminal status {current!r}")
    allowed = ALLOWED_TRANSITIONS.get(current, frozenset())
    if target not in allowed:
        raise InvalidTransition(f"transition {current!r} -> {target!r} is not allowed")


# --------------------------------------------------------------------------- #
# Repository
# --------------------------------------------------------------------------- #


class AgentJobRepository:
    """SQLite-backed repository for AgentJob records.

    Wraps a ``BridgeAdminStore`` (which owns the schema migration and the
    db path). Opens one connection per operation, with a busy timeout so
    concurrent writers wait briefly instead of failing immediately.
    """

    def __init__(self, store: BridgeAdminStore) -> None:
        self._store = store
        self._db_path = store.path

    # -- connection helper --------------------------------------------------- #

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._db_path)
        connection.row_factory = sqlite3.Row
        # Phase 1A concurrency: let a writer wait up to 5s for a lock rather
        # than raising "database is locked" immediately. The existing store
        # does not set this; set it here for the agent-job write paths.
        connection.execute("PRAGMA busy_timeout=5000")
        return connection

    # -- row coercion -------------------------------------------------------- #

    @staticmethod
    def _job_row(row: sqlite3.Row) -> AgentJob:
        return AgentJob(
            job_id=row["job_id"],
            request_type=row["request_type"],
            status=row["status"],
            model=row["model"],
            request_storage_key=row["request_storage_key"],
            created_at=row["created_at"],
            max_attempts=row["max_attempts"],
            priority=row["priority"],
            client_request_id=row["client_request_id"],
            idempotency_key=row["idempotency_key"],
            request_hash=row["request_hash"],
            account_alias=row["account_alias"],
            queued_at=row["queued_at"],
            started_at=row["started_at"],
            completed_at=row["completed_at"],
            cancel_requested_at=row["cancel_requested_at"],
            cancelled_at=row["cancelled_at"],
            expires_at=row["expires_at"],
            attempt_count=row["attempt_count"],
            error_code=row["error_code"],
            error_message=row["error_message"],
            result_id=row["result_id"],
            callback_url=row["callback_url"],
            callback_status=row["callback_status"],
            lease_owner=row["lease_owner"],
            lease_expires_at=row["lease_expires_at"],
        )

    @staticmethod
    def _event_row(row: sqlite3.Row) -> JobEvent:
        try:
            payload = json.loads(row["event_json"])
        except json.JSONDecodeError:
            payload = {}
        return JobEvent(
            event_id=row["event_id"],
            job_id=row["job_id"],
            sequence_no=row["sequence_no"],
            event_type=row["event_type"],
            event_json=payload if isinstance(payload, dict) else {},
            created_at=row["created_at"],
        )

    @staticmethod
    def _attempt_row(row: sqlite3.Row) -> JobAttempt:
        return JobAttempt(
            attempt_id=row["attempt_id"],
            job_id=row["job_id"],
            attempt_no=row["attempt_no"],
            provider=row["provider"],
            started_at=row["started_at"],
            status=row["status"],
            account_alias=row["account_alias"],
            completed_at=row["completed_at"],
            error_code=row["error_code"],
            error_message=row["error_message"],
        )

    @staticmethod
    def _result_row(row: sqlite3.Row) -> JobResult:
        return JobResult(
            result_id=row["result_id"],
            job_id=row["job_id"],
            result_type=row["result_type"],
            created_at=row["created_at"],
            text_content=row["text_content"],
            response_storage_key=row["response_storage_key"],
            model=row["model"],
            account_alias=row["account_alias"],
            finish_reason=row["finish_reason"],
        )

    # -- internal: next sequence/attempt no ---------------------------------- #

    def _next_sequence_no(self, db: sqlite3.Connection, job_id: str) -> int:
        row = db.execute(
            "SELECT COALESCE(MAX(sequence_no), 0) + 1 AS next_no FROM job_events WHERE job_id = ?",
            (job_id,),
        ).fetchone()
        return int(row["next_no"])

    def _append_event(
        self,
        db: sqlite3.Connection,
        *,
        job_id: str,
        event_type: str,
        payload: dict[str, Any] | None,
        now: str,
    ) -> None:
        # Only safe, non-secret fields are placed in event_json (status,
        # target, account, error_code). Never request bodies or headers.
        safe_payload = {
            k: v for k, v in (payload or {}).items() if k in _SAFE_EVENT_KEYS
        }
        sequence_no = self._next_sequence_no(db, job_id)
        db.execute(
            """
            INSERT INTO job_events (event_id, job_id, sequence_no, event_type, event_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                new_id("event"),
                job_id,
                sequence_no,
                event_type,
                json.dumps(safe_payload, ensure_ascii=False, sort_keys=True),
                now,
            ),
        )

    # -- job creation -------------------------------------------------------- #

    def create_job(
        self,
        *,
        request_type: str,
        model: str,
        request: Any,
        max_attempts: int = 3,
        client_request_id: str | None = None,
        idempotency_key: str | None = None,
        priority: int = 0,
        callback_url: str | None = None,
        expires_at: str | None = None,
        now: str | None = None,
    ) -> JobCreateResult:
        """Create an ``accepted`` job, or return the existing job for a
        matching idempotency key.

        Raises ``IdempotencyConflict`` when the same key is reused with a
        different request hash. The unique partial index
        ``agent_jobs_idem_idx`` is the final race-safety mechanism; a
        concurrent same-key insert surfaces as an ``IntegrityError`` that is
        resolved by loading and comparing the existing record.
        """

        now = now or utc_now()
        request_hash = canonical_request_hash(request)
        job_id = new_id("job")
        request_storage_key = f"agent-jobs/{job_id}/request.json"

        if idempotency_key:
            existing = self.get_job_by_idempotency_key(idempotency_key)
            if existing is not None:
                if (existing.request_hash or "") == request_hash:
                    return JobCreateResult(job=existing, reused=True)
                raise IdempotencyConflict(
                    f"idempotency key {idempotency_key!r} already used with a different request"
                )

        try:
            with self._connect() as db:
                db.execute(
                    """
                    INSERT INTO agent_jobs (
                        job_id, client_request_id, idempotency_key, request_hash,
                        request_type, status, priority, model, account_alias,
                        request_storage_key, created_at, attempt_count, max_attempts,
                        callback_url, expires_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        job_id,
                        client_request_id,
                        idempotency_key,
                        request_hash,
                        request_type,
                        STATUS_ACCEPTED,
                        priority,
                        model,
                        None,
                        request_storage_key,
                        now,
                        0,
                        max_attempts,
                        callback_url,
                        expires_at,
                    ),
                )
                self._append_event(
                    db,
                    job_id=job_id,
                    event_type="created",
                    payload={"status": STATUS_ACCEPTED, "request_type": request_type, "model": model},
                    now=now,
                )
        except sqlite3.IntegrityError:
            # Concurrent same-key insert won the race. Load the winner and
            # decide reuse vs conflict.
            if not idempotency_key:
                raise
            existing = self.get_job_by_idempotency_key(idempotency_key)
            if existing is None:
                raise
            if (existing.request_hash or "") == request_hash:
                return JobCreateResult(job=existing, reused=True)
            raise IdempotencyConflict(
                f"idempotency key {idempotency_key!r} already used with a different request"
            )

        return JobCreateResult(job=self.get_job(job_id), reused=False)

    # -- retrieval ----------------------------------------------------------- #

    def get_job(self, job_id: str) -> AgentJob:
        with self._connect() as db:
            row = db.execute("SELECT * FROM agent_jobs WHERE job_id = ?", (job_id,)).fetchone()
        if row is None:
            raise JobNotFound(f"job not found: {job_id}")
        return self._job_row(row)

    def get_job_optional(self, job_id: str) -> AgentJob | None:
        try:
            return self.get_job(job_id)
        except JobNotFound:
            return None

    def get_job_by_idempotency_key(self, key: str) -> AgentJob | None:
        with self._connect() as db:
            row = db.execute(
                "SELECT * FROM agent_jobs WHERE idempotency_key = ?", (key,)
            ).fetchone()
        return self._job_row(row) if row is not None else None

    # -- listing + pagination ------------------------------------------------ #

    def list_jobs(
        self,
        *,
        status: str | None = None,
        request_type: str | None = None,
        model: str | None = None,
        account: str | None = None,
        client_request_id: str | None = None,
        error_code: str | None = None,
        limit: int = 50,
        cursor: str | None = None,
    ) -> JobListPage:
        """Newest-first listing with filters and stable cursor pagination.

        The cursor encodes ``(created_at, job_id)`` as ``<created_at>|<job_id>``.
        Pagination returns rows strictly older than the cursor, so equal
        timestamps are broken by ``job_id`` descending.
        """

        safe_limit = max(1, min(int(limit), 200))
        where: list[str] = []
        params: list[Any] = []
        if status:
            where.append("status = ?")
            params.append(status)
        if request_type:
            where.append("request_type = ?")
            params.append(request_type)
        if model:
            where.append("model = ?")
            params.append(model)
        if account:
            where.append("account_alias = ?")
            params.append(account)
        if client_request_id:
            where.append("client_request_id = ?")
            params.append(client_request_id)
        if error_code:
            where.append("error_code = ?")
            params.append(error_code)
        if cursor:
            try:
                cur_created, cur_job_id = cursor.split("|", 1)
            except ValueError as exc:
                raise ValueError("invalid cursor") from exc
            where.append("(created_at < ? OR (created_at = ? AND job_id < ?))")
            params.extend([cur_created, cur_created, cur_job_id])

        where_sql = (" WHERE " + " AND ".join(where)) if where else ""
        sql = (
            f"SELECT * FROM agent_jobs{where_sql}"
            " ORDER BY created_at DESC, job_id DESC LIMIT ?"
        )
        params.append(safe_limit + 1)
        with self._connect() as db:
            rows = db.execute(sql, params).fetchall()
        has_more = len(rows) > safe_limit
        rows = rows[:safe_limit]
        jobs = [self._job_row(row) for row in rows]
        next_cursor = None
        if has_more and jobs:
            last = jobs[-1]
            next_cursor = f"{last.created_at}|{last.job_id}"
        return JobListPage(jobs=jobs, next_cursor=next_cursor, has_more=has_more)

    # -- state transitions --------------------------------------------------- #

    def transition(
        self,
        job_id: str,
        *,
        target: str,
        expected: str,
        account_alias: str | None = None,
        error_code: str | None = None,
        error_message: Any = None,
        result_id: str | None = None,
        now: str | None = None,
    ) -> AgentJob:
        """Compare-and-swap transition with a transition event.

        Validates ``expected -> target`` first, then runs
        ``UPDATE ... WHERE job_id = ? AND status = ?``. Zero rows affected
        means either the job is missing or the expected status no longer
        matches (race); both are reported distinctly.
        """

        validate_transition(expected, target)
        now = now or utc_now()
        timestamp_column = _TIMESTAMP_COLUMN_FOR_TARGET.get(target)
        safe_message = sanitize_error(error_message, code=error_code) if error_message else None

        set_clauses = ["status = ?"]
        params: list[Any] = [target]
        if timestamp_column:
            set_clauses.append(f"{timestamp_column} = ?")
            params.append(now)
        if account_alias is not None:
            set_clauses.append("account_alias = ?")
            params.append(account_alias)
        if error_code is not None:
            set_clauses.append("error_code = ?")
            params.append(error_code)
        if safe_message is not None:
            set_clauses.append("error_message = ?")
            params.append(safe_message)
        if result_id is not None:
            set_clauses.append("result_id = ?")
            params.append(result_id)
        # Clear lease fields when leaving an active execution state.
        if expected in ACTIVE_EXECUTION_STATUSES and target not in ACTIVE_EXECUTION_STATUSES:
            set_clauses.append("lease_owner = NULL")
            set_clauses.append("lease_expires_at = NULL")

        params.extend([job_id, expected])
        sql = (
            "UPDATE agent_jobs SET " + ", ".join(set_clauses) + " WHERE job_id = ? AND status = ?"
        )

        with self._connect() as db:
            cursor = db.execute(sql, params)
            if cursor.rowcount == 0:
                # Distinguish not-found from race.
                existing = db.execute(
                    "SELECT status FROM agent_jobs WHERE job_id = ?", (job_id,)
                ).fetchone()
                if existing is None:
                    raise JobNotFound(f"job not found: {job_id}")
                raise InvalidTransition(
                    f"transition {expected!r} -> {target!r} lost the race "
                    f"(job is now {existing['status']!r})"
                )
            self._append_event(
                db,
                job_id=job_id,
                event_type="transition",
                payload={
                    "from": expected,
                    "to": target,
                    "account": account_alias,
                    "error_code": error_code,
                },
                now=now,
            )
        return self.get_job(job_id)

    # -- events -------------------------------------------------------------- #

    def list_events(self, job_id: str) -> list[JobEvent]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT * FROM job_events WHERE job_id = ? ORDER BY sequence_no ASC",
                (job_id,),
            ).fetchall()
        return [self._event_row(row) for row in rows]

    # -- attempts ------------------------------------------------------------ #

    def _next_attempt_no(self, db: sqlite3.Connection, job_id: str) -> int:
        row = db.execute(
            "SELECT COALESCE(MAX(attempt_no), 0) + 1 AS next_no FROM job_attempts WHERE job_id = ?",
            (job_id,),
        ).fetchone()
        return int(row["next_no"])

    def start_attempt(
        self,
        job_id: str,
        *,
        provider: str = "chatgpt",
        account_alias: str | None = None,
        now: str | None = None,
    ) -> JobAttempt:
        """Append an immutable attempt row and increment ``attempt_count``.

        The attempt number is derived from the post-increment count so the
        job row and attempt row stay consistent. The unique
        ``(job_id, attempt_no)`` index plus the single transaction make
        duplicate attempt numbers impossible in the single-process model.
        """

        now = now or utc_now()
        with self._connect() as db:
            db.execute(
                "UPDATE agent_jobs SET attempt_count = attempt_count + 1 WHERE job_id = ?",
                (job_id,),
            )
            row = db.execute(
                "SELECT attempt_count FROM agent_jobs WHERE job_id = ?", (job_id,)
            ).fetchone()
            if row is None:
                raise JobNotFound(f"job not found: {job_id}")
            attempt_no = int(row["attempt_count"])
            attempt_id = new_id("attempt")
            if account_alias is not None:
                db.execute(
                    "UPDATE agent_jobs SET account_alias = ? WHERE job_id = ?",
                    (account_alias, job_id),
                )
            db.execute(
                """
                INSERT INTO job_attempts (
                    attempt_id, job_id, attempt_no, account_alias, provider,
                    started_at, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (attempt_id, job_id, attempt_no, account_alias, provider, now, STATUS_RUNNING),
            )
            self._append_event(
                db,
                job_id=job_id,
                event_type="attempt_started",
                payload={"attempt_no": attempt_no, "account": account_alias, "provider": provider},
                now=now,
            )
            attempt = JobAttempt(
                attempt_id=attempt_id,
                job_id=job_id,
                attempt_no=attempt_no,
                provider=provider,
                started_at=now,
                status=STATUS_RUNNING,
                account_alias=account_alias,
            )
        return attempt

    def finish_attempt(
        self,
        job_id: str,
        attempt_no: int,
        *,
        status: str,
        error_code: str | None = None,
        error_message: Any = None,
        now: str | None = None,
    ) -> JobAttempt:
        """Mark an attempt terminal with redacted error data."""

        if status not in {STATUS_SUCCEEDED, STATUS_FAILED, STATUS_CANCELLED}:
            raise InvalidTransition(f"attempt finish status must be terminal, got {status!r}")
        now = now or utc_now()
        safe_message = sanitize_error(error_message, code=error_code) if error_message else None
        with self._connect() as db:
            cursor = db.execute(
                """
                UPDATE job_attempts SET completed_at = ?, status = ?, error_code = ?, error_message = ?
                WHERE job_id = ? AND attempt_no = ?
                """,
                (now, status, error_code, safe_message, job_id, attempt_no),
            )
            if cursor.rowcount == 0:
                raise JobNotFound(f"attempt not found: job={job_id} no={attempt_no}")
            self._append_event(
                db,
                job_id=job_id,
                event_type="attempt_finished",
                payload={"attempt_no": attempt_no, "status": status, "error_code": error_code},
                now=now,
            )
            row = db.execute(
                "SELECT * FROM job_attempts WHERE job_id = ? AND attempt_no = ?",
                (job_id, attempt_no),
            ).fetchone()
        return self._attempt_row(row)

    def list_attempts(self, job_id: str) -> list[JobAttempt]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT * FROM job_attempts WHERE job_id = ? ORDER BY attempt_no ASC",
                (job_id,),
            ).fetchall()
        return [self._attempt_row(row) for row in rows]

    # -- results ------------------------------------------------------------- #

    def save_result(
        self,
        job_id: str,
        *,
        result_type: str,
        text_content: str | None = None,
        response_storage_key: str | None = None,
        model: str | None = None,
        account_alias: str | None = None,
        finish_reason: str | None = None,
        now: str | None = None,
    ) -> JobResult:
        """Save one result per job. ``job_results.job_id`` is UNIQUE, so a
        duplicate final-result insert deterministically raises. Large
        response bodies are referenced by ``response_storage_key``; no binary
        blobs are stored in SQLite.
        """

        now = now or utc_now()
        result_id = new_id("result")
        with self._connect() as db:
            try:
                db.execute(
                    """
                    INSERT INTO job_results (
                        result_id, job_id, result_type, text_content,
                        response_storage_key, model, account_alias, finish_reason, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        result_id,
                        job_id,
                        result_type,
                        text_content,
                        response_storage_key,
                        model,
                        account_alias,
                        finish_reason,
                        now,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise IdempotencyConflict(
                    f"a result already exists for job {job_id}"
                ) from exc
            db.execute(
                "UPDATE agent_jobs SET result_id = ? WHERE job_id = ?",
                (result_id, job_id),
            )
        return JobResult(
            result_id=result_id,
            job_id=job_id,
            result_type=result_type,
            created_at=now,
            text_content=text_content,
            response_storage_key=response_storage_key,
            model=model,
            account_alias=account_alias,
            finish_reason=finish_reason,
        )

    def get_result(self, job_id: str) -> JobResult | None:
        with self._connect() as db:
            row = db.execute(
                "SELECT * FROM job_results WHERE job_id = ?", (job_id,)
            ).fetchone()
        return self._result_row(row) if row is not None else None

    # -- artifacts ----------------------------------------------------------- #

    def record_artifact(
        self,
        job_id: str,
        *,
        asset: dict[str, Any],
        kind: str,
        account: str | None = None,
        prompt: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Associate an artifact with a job via the existing artifacts table."""

        self._store.record_artifact(
            asset,
            kind=kind,
            account=account,
            prompt=prompt,
            metadata=metadata,
            job_id=job_id,
        )

    def list_artifacts(self, job_id: str) -> list[dict[str, Any]]:
        return self._store.list_artifacts_by_job(job_id)

    # -- cancellation -------------------------------------------------------- #

    def request_cancel(self, job_id: str, *, now: str | None = None) -> AgentJob:
        """Persist a cancellation request. No provider stop is invoked.

        Terminal jobs reject cancellation per the state-machine contract.
        Compare-and-swap on the current status makes concurrent cancels safe.
        """

        now = now or utc_now()
        job = self.get_job(job_id)
        if job.status in TERMINAL_STATUSES:
            raise InvalidTransition(
                f"cannot cancel job in terminal status {job.status!r}"
            )
        if job.status not in CANCELLABLE_STATUSES:
            raise InvalidTransition(
                f"cannot cancel job in status {job.status!r}"
            )
        if job.status == STATUS_CANCEL_REQUESTED:
            # Idempotent: already requested.
            return job
        with self._connect() as db:
            cursor = db.execute(
                """
                UPDATE agent_jobs
                SET status = ?, cancel_requested_at = ?
                WHERE job_id = ? AND status = ?
                """,
                (STATUS_CANCEL_REQUESTED, now, job_id, job.status),
            )
            if cursor.rowcount == 0:
                raise InvalidTransition(
                    f"cancel lost the race (job {job_id} is no longer {job.status!r})"
                )
            self._append_event(
                db,
                job_id=job_id,
                event_type="cancel_requested",
                payload={"from": job.status},
                now=now,
            )
        return self.get_job(job_id)

    # -- lease claim + renewal ---------------------------------------------- #

    def claim_job(
        self,
        job_id: str,
        *,
        lease_owner: str,
        lease_expires_at: str,
        account_alias: str | None = None,
        provider: str = "chatgpt",
        now: str | None = None,
    ) -> ClaimOutcome | None:
        """Atomically claim a queued job: ``queued -> running``.

        Sets lease fields, sets ``started_at`` on first start, increments
        ``attempt_count``, and creates an attempt row in the same
        transaction. Returns ``None`` when the job is missing, not queued,
        or the compare-and-swap lost a race (so two concurrent claimers
        cannot both succeed).
        """

        now = now or utc_now()
        with self._connect() as db:
            cursor = db.execute(
                """
                UPDATE agent_jobs
                SET status = ?,
                    lease_owner = ?,
                    lease_expires_at = ?,
                    started_at = COALESCE(started_at, ?),
                    account_alias = COALESCE(account_alias, ?),
                    attempt_count = attempt_count + 1
                WHERE job_id = ? AND status = ?
                """,
                (
                    STATUS_RUNNING,
                    lease_owner,
                    lease_expires_at,
                    now,
                    account_alias,
                    job_id,
                    STATUS_QUEUED,
                ),
            )
            if cursor.rowcount == 0:
                return None
            row = db.execute(
                "SELECT attempt_count FROM agent_jobs WHERE job_id = ?", (job_id,)
            ).fetchone()
            attempt_no = int(row["attempt_count"])
            attempt_id = new_id("attempt")
            db.execute(
                """
                INSERT INTO job_attempts (
                    attempt_id, job_id, attempt_no, account_alias, provider,
                    started_at, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (attempt_id, job_id, attempt_no, account_alias, provider, now, STATUS_RUNNING),
            )
            self._append_event(
                db,
                job_id=job_id,
                event_type="attempt_started",
                payload={"attempt_no": attempt_no, "account": account_alias, "provider": provider},
                now=now,
            )
        return ClaimOutcome(job_id=job_id, attempt_no=attempt_no)

    def renew_lease(
        self,
        job_id: str,
        *,
        lease_owner: str,
        lease_expires_at: str,
        now: str | None = None,
    ) -> bool:
        """Renew a lease only when the job is actively executing and the
        owner matches. Returns False if the owner does not match or the job
        is not executing (lease superseded / finished).
        """

        now = now or utc_now()
        with self._connect() as db:
            cursor = db.execute(
                """
                UPDATE agent_jobs
                SET lease_expires_at = ?
                WHERE job_id = ?
                  AND lease_owner = ?
                  AND status IN (?, ?)
                """,
                (lease_expires_at, job_id, lease_owner, STATUS_RUNNING, STATUS_STREAMING),
            )
            return cursor.rowcount == 1

    # -- restart-recovery sweep --------------------------------------------- #

    def recover_stale_jobs(self, *, now: str | None = None) -> RecoverySummary:
        """Detect jobs stuck in ``running``/``streaming`` with an expired
        lease and move them to a safe state.

        - attempts remaining (``attempt_count < max_attempts``): re-queue
          (``-> queued``), clear lease, keep ``started_at``.
        - attempts exhausted: ``-> failed`` with ``error_code=worker_crash``,
          clear lease, set ``completed_at``.

        Recovery transitions use compare-and-swap on the current status, so
        running the sweep twice is idempotent: the second pass finds the jobs
        no longer in ``running``/``streaming``. No provider stop is invoked.
        Invoked only by tests in this phase; not wired to startup.
        """

        now = now or utc_now()
        summary = RecoverySummary()
        with self._connect() as db:
            stale = db.execute(
                """
                SELECT job_id, status, attempt_count, max_attempts
                FROM agent_jobs
                WHERE status IN (?, ?)
                  AND lease_expires_at IS NOT NULL
                  AND lease_expires_at < ?
                """,
                (STATUS_RUNNING, STATUS_STREAMING, now),
            ).fetchall()
            for row in stale:
                job_id = row["job_id"]
                current = row["status"]
                attempts = int(row["attempt_count"])
                max_attempts = int(row["max_attempts"])
                if attempts < max_attempts:
                    db.execute(
                        """
                        UPDATE agent_jobs
                        SET status = ?, queued_at = ?, lease_owner = NULL, lease_expires_at = NULL
                        WHERE job_id = ? AND status = ?
                        """,
                        (STATUS_QUEUED, now, job_id, current),
                    )
                    self._append_event(
                        db,
                        job_id=job_id,
                        event_type="recovery_requeued",
                        payload={"from": current, "error_code": "worker_crash"},
                        now=now,
                    )
                    summary.requeued.append(job_id)
                else:
                    db.execute(
                        """
                        UPDATE agent_jobs
                        SET status = ?, completed_at = ?, error_code = ?,
                            lease_owner = NULL, lease_expires_at = NULL
                        WHERE job_id = ? AND status = ?
                        """,
                        (STATUS_FAILED, now, "worker_crash", job_id, current),
                    )
                    self._append_event(
                        db,
                        job_id=job_id,
                        event_type="recovery_failed",
                        payload={"from": current, "error_code": "worker_crash"},
                        now=now,
                    )
                    summary.failed.append(job_id)
        return summary


# --------------------------------------------------------------------------- #
# Module-private lookup tables
# --------------------------------------------------------------------------- #

# Timestamp column written when entering a target state.
_TIMESTAMP_COLUMN_FOR_TARGET: dict[str, str] = {
    STATUS_QUEUED: "queued_at",
    STATUS_RUNNING: "started_at",
    STATUS_SUCCEEDED: "completed_at",
    STATUS_FAILED: "completed_at",
    STATUS_CANCELLED: "cancelled_at",
    STATUS_EXPIRED: "completed_at",
}

# Keys permitted in event_json. Whitelist keeps request bodies and headers
# out of the event log.
_SAFE_EVENT_KEYS = frozenset(
    {
        "status",
        "request_type",
        "model",
        "from",
        "to",
        "account",
        "attempt_no",
        "provider",
        "error_code",
        "result_type",
    }
)
