"""Phase 1B additive HTTP route service for Agent Jobs.

Owns request validation, normalization, idempotency-header precedence,
atomic request-file persistence, safe public serialization, list-filter
parsing, and domain-exception → HTTP mapping. It does NOT own the SQLite
schema, state machine, repository internals, provider execution, account
routing, or HTTP socket handling (those stay in ``agent_jobs.py`` /
``admin_store.py`` / ``openai_compat.py``).

Phase 1B scope:
- only ``chat`` and ``deep_research`` submissions
- submission progresses ``accepted -> validating -> queued`` synchronously
- queued jobs are NOT executed (Phase 1C introduces the coordinator)
- events returned as JSON only (no SSE)
- cancellation stops at ``cancel_requested`` (never ``cancelled``)
- shared Bearer key only (no agent/operator isolation)

No provider, router, limiter, transport, or background thread is used.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

from chatgpt_api.api.agent_jobs import (
    ALL_STATUSES,
    AgentJobRepository,
    IdempotencyConflict,
    InvalidTransition,
    JobNotFound,
    STATUS_ACCEPTED,
    STATUS_CANCELLED,
    STATUS_CANCEL_REQUESTED,
    STATUS_EXPIRED,
    STATUS_FAILED,
    STATUS_QUEUED,
    STATUS_VALIDATING,
)
from chatgpt_api.api.text_execution import (
    TextExecutionStorageError,
    load_response_json,
    request_file_path,
)

SUPPORTED_JOB_TYPES = ("chat", "deep_research")
DEEP_RESEARCH_MODEL = "chatgpt-deep-research"

_ALLOWED_ROLES = ("system", "user", "assistant", "tool")
_MAX_STRING = 256
_MAX_ATTEMPTS_MIN = 1
_MAX_ATTEMPTS_MAX = 10
_DEFAULT_MAX_ATTEMPTS = 3
_EVENT_LIST_LIMIT = 200
_ISO_UTC_RE = __import__("re").compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

# Approved request fields per type. Any other field is rejected so clients
# do not assume unsupported execution knobs work.
_CHAT_FIELDS = frozenset(
    {"type", "model", "messages", "stream", "client_request_id", "idempotency_key", "max_attempts", "expires_at"}
)
_RESEARCH_FIELDS = frozenset(
    {"type", "model", "messages", "client_request_id", "idempotency_key", "max_attempts", "expires_at"}
)


# --------------------------------------------------------------------------- #
# Error envelope
# --------------------------------------------------------------------------- #


def build_error(code: str, message: str, *, type_: str = "invalid_request_error") -> dict[str, Any]:
    return {"error": {"type": type_, "code": code, "message": message}}


def _not_found(message: str = "job not found") -> tuple[int, dict[str, Any]]:
    return 404, build_error("not_found", message, type_="not_found")


# --------------------------------------------------------------------------- #
# Validation + normalization
# --------------------------------------------------------------------------- #


class ValidationError(ValueError):
    """Raised for 400-class request validation failures."""

    def __init__(self, message: str, *, code: str = "invalid_request_error") -> None:
        super().__init__(message)
        self.code = code


def _require_str(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{name} must be a non-empty string")
    return value


def _require_bounded_str(value: Any, name: str) -> str:
    text = _require_str(value, name)
    if len(text) > _MAX_STRING:
        raise ValidationError(f"{name} is too long (max {_MAX_STRING} characters)")
    return text


def _validate_messages(messages: Any) -> list[dict[str, Any]]:
    if not isinstance(messages, list) or not messages:
        raise ValidationError("messages must be a non-empty array")
    cleaned: list[dict[str, Any]] = []
    for idx, msg in enumerate(messages):
        if not isinstance(msg, dict):
            raise ValidationError(f"messages[{idx}] must be an object")
        role = msg.get("role")
        if role not in _ALLOWED_ROLES:
            raise ValidationError(
                f"messages[{idx}].role must be one of {', '.join(_ALLOWED_ROLES)}", code="invalid_request_error"
            )
        content = msg.get("content")
        # Phase 1B: string content only. Multimodal arrays are rejected.
        if not isinstance(content, str):
            raise ValidationError(
                f"messages[{idx}].content must be a string in Phase 1B (multimodal input is deferred)",
                code="invalid_request_error",
            )
        if role != "tool" and not content.strip():
            raise ValidationError(f"messages[{idx}].content must not be blank")
        cleaned.append({"role": role, "content": content})
    return cleaned


def _validate_max_attempts(value: Any) -> int:
    if value is None:
        return _DEFAULT_MAX_ATTEMPTS
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValidationError("max_attempts must be an integer")
    if not (_MAX_ATTEMPTS_MIN <= value <= _MAX_ATTEMPTS_MAX):
        raise ValidationError(
            f"max_attempts must be between {_MAX_ATTEMPTS_MIN} and {_MAX_ATTEMPTS_MAX}"
        )
    return value


def _validate_expires_at(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not _ISO_UTC_RE.match(value):
        raise ValidationError("expires_at must be null or an ISO-8601 UTC timestamp like 2026-06-27T12:00:00Z")
    return value


def _validate_optional_id(value: Any, name: str) -> str | None:
    if value is None:
        return None
    return _require_bounded_str(value, name) or None


def _reject_unknown_fields(body: dict[str, Any], allowed: frozenset[str]) -> None:
    extra = set(body.keys()) - allowed
    if extra:
        raise ValidationError(
            f"unsupported field(s): {', '.join(sorted(extra))}", code="invalid_request_error"
        )


def normalize_request(body: Any) -> tuple[dict[str, Any], str, int, str | None, str | None]:
    """Validate and normalize a submission body.

    Returns ``(normalized_request, request_type, max_attempts, expires_at,
    body_idempotency_key)``. The ``idempotency_key`` is intentionally NOT
    included in ``normalized_request`` so semantic hashing is stable
    regardless of whether the key arrived via header or body (transport
    metadata is stripped before hashing/persistence).
    """

    if not isinstance(body, dict):
        raise ValidationError("request body must be a JSON object")
    job_type = body.get("type")
    if job_type not in SUPPORTED_JOB_TYPES:
        raise ValidationError(
            f"unsupported job type {job_type!r}; supported types: {', '.join(SUPPORTED_JOB_TYPES)} "
            f"(image_generation, image_edit, vision are deferred to Phase 2)",
            code="unsupported_job_type",
        )
    if job_type == "chat":
        _reject_unknown_fields(body, _CHAT_FIELDS)
        model = _require_str(body.get("model"), "model")
        messages = _validate_messages(body.get("messages"))
        stream = body.get("stream", False)
        if not isinstance(stream, bool):
            raise ValidationError("stream must be a boolean")
        normalized: dict[str, Any] = {
            "type": "chat",
            "model": model,
            "messages": messages,
            "stream": stream,
        }
    else:  # deep_research
        _reject_unknown_fields(body, _RESEARCH_FIELDS)
        model = body.get("model")
        if model != DEEP_RESEARCH_MODEL:
            raise ValidationError(
                f"deep_research jobs require model {DEEP_RESEARCH_MODEL!r}", code="invalid_request_error"
            )
        messages = _validate_messages(body.get("messages"))
        normalized = {"type": "deep_research", "model": DEEP_RESEARCH_MODEL, "messages": messages}

    client_request_id = _validate_optional_id(body.get("client_request_id"), "client_request_id")
    if client_request_id:
        normalized["client_request_id"] = client_request_id
    body_idem = _validate_optional_id(body.get("idempotency_key"), "idempotency_key")
    max_attempts = _validate_max_attempts(body.get("max_attempts"))
    expires_at = _validate_expires_at(body.get("expires_at"))
    normalized["max_attempts"] = max_attempts
    if expires_at:
        normalized["expires_at"] = expires_at
    return normalized, job_type, max_attempts, expires_at, body_idem


# --------------------------------------------------------------------------- #
# Atomic request persistence
# --------------------------------------------------------------------------- #


def write_request_json(output_root: Path, job_id: str, normalized_request: dict[str, Any]) -> None:
    """Atomically persist the normalized request as UTF-8 JSON.

    Writes to a same-directory temp file then ``os.replace`` (atomic rename
    on POSIX; atomic for same-volume renames on Windows). Temp file is
    removed on failure. Stores only the normalized semantic request — no
    auth headers, cookies, API keys, capture contents, or transport metadata.
    """

    target = request_file_path(output_root, job_id)
    target.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(normalized_request, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    tmp = target.with_name(f"{target.name}.tmp.{os.getpid()}")
    try:
        with open(tmp, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, target)
    except Exception:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass
        raise


# --------------------------------------------------------------------------- #
# Safe serializers (explicit allowlists)
# --------------------------------------------------------------------------- #


def serialize_submission(job) -> dict[str, Any]:
    base = f"/v1/agent/jobs/{job.job_id}"
    return {
        "job_id": job.job_id,
        "status": job.status,
        "type": job.request_type,
        "created_at": job.created_at,
        "status_url": base,
        "result_url": f"{base}/result",
        "events_url": f"{base}/events",
        "artifacts_url": f"{base}/artifacts",
    }


def serialize_status(job, *, artifact_count: int = 0) -> dict[str, Any]:
    error = None
    if job.error_code:
        error = {"code": job.error_code, "message": job.error_message or ""}
    return {
        "job_id": job.job_id,
        "type": job.request_type,
        "status": job.status,
        "model": job.model,
        "account_alias": job.account_alias,
        "attempt_count": job.attempt_count,
        "max_attempts": job.max_attempts,
        "client_request_id": job.client_request_id,
        "created_at": job.created_at,
        "queued_at": job.queued_at,
        "started_at": job.started_at,
        "completed_at": job.completed_at,
        "cancel_requested_at": job.cancel_requested_at,
        "cancelled_at": job.cancelled_at,
        "expires_at": job.expires_at,
        "result_available": job.result_id is not None,
        "artifact_count": artifact_count,
        "error": error,
    }


def serialize_result(
    result,
    response: dict[str, Any] | None = None,
    artifacts: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    # Never expose response_storage_key (filesystem path).
    payload: dict[str, Any] = {
        "job_id": result.job_id,
        "result_type": result.result_type,
        "created_at": result.created_at,
    }
    if result.text_content is not None:
        payload["text"] = result.text_content
    if result.model is not None:
        payload["model"] = result.model
    if result.account_alias is not None:
        payload["account_alias"] = result.account_alias
    if result.finish_reason is not None:
        payload["finish_reason"] = result.finish_reason
    if response is not None:
        payload["response"] = response
    if artifacts is not None:
        payload["artifacts"] = [serialize_artifact(artifact) for artifact in artifacts]
    return payload


def serialize_event(event) -> dict[str, Any]:
    return {
        "event_id": event.event_id,
        "sequence_no": event.sequence_no,
        "event_type": event.event_type,
        "data": event.event_json,
        "created_at": event.created_at,
    }


def serialize_artifact(artifact: dict[str, Any]) -> dict[str, Any]:
    # Build a relative download URL; never expose the filesystem path.
    file_id = artifact.get("file_id") or ""
    filename = artifact.get("filename") or "download"
    return {
        "file_id": file_id,
        "filename": filename,
        "download_url": f"/v1/chatgpt/files/{file_id}/{filename}",
        "content_type": artifact.get("content_type") or "application/octet-stream",
        "bytes": artifact.get("bytes"),
        "created_at": artifact.get("created_at"),
    }


# --------------------------------------------------------------------------- #
# Route service
# --------------------------------------------------------------------------- #


class AgentJobRouteService:
    """HTTP-independent route service. Returns ``(status_code, payload)``.

    Constructed per request by the facade with a fresh repository (matching
    the existing one-connection-per-op store pattern).
    """

    def __init__(
        self,
        repo: AgentJobRepository,
        output_root: Path,
        wake_callback: Callable[[], None] | None = None,
        cancel_callback: Callable[[Any], None] | None = None,
    ) -> None:
        self._repo = repo
        self._output_root = output_root
        self._wake_callback = wake_callback
        self._cancel_callback = cancel_callback

    # -- submission ---------------------------------------------------------- #

    def submit(
        self,
        body: Any,
        idempotency_header: str | None,
    ) -> tuple[int, dict[str, Any]]:
        try:
            normalized, job_type, max_attempts, expires_at, body_idem = normalize_request(body)
        except ValidationError as exc:
            return 400, build_error(exc.code, str(exc))

        # Header takes precedence over body for key selection.
        effective_key = (idempotency_header or body_idem or None)
        if idempotency_header and body_idem and idempotency_header != body_idem:
            # Body value is ignored for key selection when header is present.
            pass

        try:
            create = self._repo.create_job(
                request_type=job_type,
                model=normalized["model"],
                request=normalized,
                max_attempts=max_attempts,
                client_request_id=normalized.get("client_request_id"),
                idempotency_key=effective_key,
                expires_at=expires_at,
            )
        except IdempotencyConflict:
            return 409, build_error("idempotency_conflict", "idempotency key already used with a different request")
        except Exception as exc:  # noqa: BLE001
            return 500, build_error("internal_error", "could not create job", type_="internal_error")

        if create.reused:
            # Idempotent reuse: do not rewrite, re-transition, or duplicate
            # events. Verify the request file is still present; if it is
            # missing, surface a storage consistency failure rather than
            # pretending the job is healthy (smallest safe design).
            request_path = request_file_path(self._output_root, create.job.job_id)
            if not request_path.exists():
                return 500, {
                    "job_id": create.job.job_id,
                    "error": {"type": "internal_error", "code": "storage_failure", "message": "request file for this job is missing"},
                }
            return 200, serialize_submission(create.job)

        job = create.job
        try:
            self._repo.transition(job.job_id, target=STATUS_VALIDATING, expected=STATUS_ACCEPTED)
            write_request_json(self._output_root, job.job_id, normalized)
        except Exception:
            # Storage failure during validation: transition to failed with a
            # redacted error. validating -> failed is an allowed transition.
            try:
                self._repo.transition(
                    job.job_id,
                    target=STATUS_FAILED,
                    expected=STATUS_VALIDATING,
                    error_code="storage_failure",
                    error_message="could not persist request payload",
                )
            except Exception:
                pass
            return 500, {
                "job_id": job.job_id,
                "error": {"type": "internal_error", "code": "storage_failure", "message": "could not persist request payload"},
            }
        try:
            job = self._repo.transition(job.job_id, target=STATUS_QUEUED, expected=STATUS_VALIDATING)
        except Exception as exc:  # noqa: BLE001
            return 500, build_error("internal_error", "could not queue job", type_="internal_error")
        self._wake_coordinator()

        return 201, serialize_submission(job)

    # -- list ---------------------------------------------------------------- #

    def list_jobs(self, query: dict[str, list[str]]) -> tuple[int, dict[str, Any]]:
        try:
            filters = _parse_list_query(query)
        except ValidationError as exc:
            return 400, build_error(exc.code, str(exc))
        page = self._repo.list_jobs(**filters)
        return 200, {
            "jobs": [serialize_status(job) for job in page.jobs],
            "next_cursor": page.next_cursor,
            "has_more": page.has_more,
        }

    # -- status -------------------------------------------------------------- #

    def get_status(self, job_id: str) -> tuple[int, dict[str, Any]]:
        try:
            job = self._repo.get_job(job_id)
        except JobNotFound:
            return _not_found()
        artifact_count = len(self._repo.list_artifacts(job_id))
        return 200, serialize_status(job, artifact_count=artifact_count)

    # -- result -------------------------------------------------------------- #

    def get_result(self, job_id: str) -> tuple[int, dict[str, Any]]:
        try:
            job = self._repo.get_job(job_id)
        except JobNotFound:
            return _not_found()
        result = self._repo.get_result(job_id)
        if result is None:
            if job.status == STATUS_FAILED:
                return 409, build_error(
                    "job_failed",
                    f"job failed without a result: {job.error_code or 'unknown'}",
                )
            return 409, build_error("pending", "The job result is not available yet.")
        response = None
        if result.response_storage_key:
            try:
                response = load_response_json(self._output_root.parent, result.response_storage_key)
            except TextExecutionStorageError:
                return 500, build_error(
                    "storage_failure",
                    "job result payload is missing or invalid",
                    type_="internal_error",
                )
        artifacts = None
        if result.result_type == "research":
            artifacts = self._repo.list_artifacts(job_id)
            if not artifacts:
                return 500, build_error(
                    "storage_failure",
                    "job research artifact is missing or invalid",
                    type_="internal_error",
                )
        return 200, serialize_result(result, response, artifacts)

    # -- events -------------------------------------------------------------- #

    def get_events(self, job_id: str) -> tuple[int, dict[str, Any]]:
        try:
            self._repo.get_job(job_id)
        except JobNotFound:
            return _not_found()
        events = self._repo.list_events(job_id)[:_EVENT_LIST_LIMIT]
        return 200, {
            "job_id": job_id,
            "events": [serialize_event(event) for event in events],
            "next_cursor": None,
            "has_more": False,
        }

    # -- artifacts ----------------------------------------------------------- #

    def get_artifacts(self, job_id: str) -> tuple[int, dict[str, Any]]:
        try:
            self._repo.get_job(job_id)
        except JobNotFound:
            return _not_found()
        artifacts = self._repo.list_artifacts(job_id)
        return 200, {
            "job_id": job_id,
            "artifacts": [serialize_artifact(a) for a in artifacts],
        }

    # -- cancel -------------------------------------------------------------- #

    def cancel(self, job_id: str) -> tuple[int, dict[str, Any]]:
        try:
            job = self._repo.request_cancel(job_id)
        except JobNotFound:
            return _not_found()
        except InvalidTransition:
            return 409, build_error(
                "cancel_conflict",
                "job is not in a cancellable state",
            )
        if self._cancel_callback is not None:
            try:
                self._cancel_callback(job)
            except Exception:
                pass
        self._wake_coordinator()
        return 200, {
            "job_id": job.job_id,
            "status": job.status,
            "cancel_requested_at": job.cancel_requested_at,
            "message": "Cancellation has been recorded. Final cancellation resolution requires the execution coordinator.",
        }

    def _wake_coordinator(self) -> None:
        if self._wake_callback is None:
            return
        try:
            self._wake_callback()
        except Exception:
            pass

    # -- dispatch ------------------------------------------------------------ #

    def handle_get(self, path: str, query: dict[str, list[str]]) -> tuple[int, dict[str, Any]]:
        parsed = _parse_agent_path(path)
        if parsed is None:
            return _not_found("route not found")
        job_id, sub = parsed
        if sub == "list":
            return self.list_jobs(query)
        if job_id is None:
            return _not_found("route not found")
        if sub == "":
            return self.get_status(job_id)
        if sub == "result":
            return self.get_result(job_id)
        if sub == "events":
            return self.get_events(job_id)
        if sub == "artifacts":
            return self.get_artifacts(job_id)
        return _not_found("route not found")

    def handle_post(self, path: str, body: Any, idempotency_header: str | None) -> tuple[int, dict[str, Any]]:
        parsed = _parse_agent_path(path)
        if parsed is None:
            return _not_found("route not found")
        job_id, sub = parsed
        if sub == "list" and job_id is None:
            return self.submit(body, idempotency_header)
        if sub == "cancel" and job_id is not None:
            return self.cancel(job_id)
        return _not_found("route not found")


# --------------------------------------------------------------------------- #
# Query/path parsing
# --------------------------------------------------------------------------- #


def _first(query: dict[str, list[str]], key: str) -> str | None:
    values = query.get(key)
    if not values:
        return None
    value = values[-1]
    return value if isinstance(value, str) else None


def _parse_list_query(query: dict[str, list[str]]) -> dict[str, Any]:
    filters: dict[str, Any] = {}
    status = _first(query, "status")
    if status is not None:
        if status not in ALL_STATUSES:
            raise ValidationError(f"invalid status filter: {status!r}")
        filters["status"] = status
    job_type = _first(query, "type")
    if job_type is not None:
        if job_type not in SUPPORTED_JOB_TYPES:
            raise ValidationError(
                f"invalid type filter: {job_type!r}; supported: {', '.join(SUPPORTED_JOB_TYPES)}"
            )
        filters["request_type"] = job_type
    model = _first(query, "model")
    if model is not None:
        filters["model"] = model
    account = _first(query, "account")
    if account is not None:
        filters["account"] = account
    client_request_id = _first(query, "client_request_id")
    if client_request_id is not None:
        filters["client_request_id"] = client_request_id
    error_code = _first(query, "error_code")
    if error_code is not None:
        filters["error_code"] = error_code
    limit_str = _first(query, "limit")
    if limit_str is not None:
        try:
            filters["limit"] = int(limit_str)
        except ValueError as exc:
            raise ValidationError("limit must be an integer") from exc
    cursor = _first(query, "cursor")
    if cursor is not None:
        if "|" not in cursor:
            raise ValidationError("malformed cursor")
        filters["cursor"] = cursor
    return filters


def _parse_agent_path(path: str) -> tuple[str | None, str] | None:
    """Parse an agent-jobs path into ``(job_id, sub)``.

    ``sub`` is ``"list"`` for the collection, ``""`` for the bare job, or a
    sub-resource name (``result``/``events``/``artifacts``/``cancel``).
    Returns ``None`` if the path shape is unrecognized.
    """

    if path == "/v1/agent/jobs":
        return (None, "list")
    prefix = "/v1/agent/jobs/"
    if not path.startswith(prefix):
        return None
    rest = path[len(prefix):]
    if not rest:
        return None
    parts = rest.split("/")
    if len(parts) == 1 and parts[0]:
        return (parts[0], "")
    if len(parts) == 2 and parts[0] and parts[1]:
        return (parts[0], parts[1])
    return None
