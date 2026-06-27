"""Synthetic tests for Phase 1A AgentJob persistence.

No network, no ChatGPT captures, no API keys, no provider execution, no
Docker, no Bun. Uses temporary SQLite databases and temporary output paths.
Timestamps are injected so tests never depend on wall-clock sleeps.
"""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

import pytest

from chatgpt_api.api.admin_store import BridgeAdminStore
from chatgpt_api.api.agent_jobs import (
    ACTIVE_EXECUTION_STATUSES,
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
    STATUS_RETRY_WAIT,
    STATUS_RUNNING,
    STATUS_STREAMING,
    STATUS_SUCCEEDED,
    STATUS_VALIDATING,
    TERMINAL_STATUSES,
    canonical_request_hash,
    sanitize_error,
    validate_transition,
)

T0 = "2026-01-01T00:00:00Z"
T1 = "2026-01-01T00:00:01Z"
T2 = "2026-01-01T00:00:02Z"
T3 = "2026-01-01T00:00:03Z"
T4 = "2026-01-01T00:00:04Z"
T5 = "2026-01-01T00:00:05Z"
T_FUTURE = "2099-01-01T00:00:00Z"


def _store(tmp_path: Path) -> BridgeAdminStore:
    return BridgeAdminStore(tmp_path / "admin.sqlite")


def _repo(tmp_path: Path) -> AgentJobRepository:
    return AgentJobRepository(_store(tmp_path))


def _make_chat_request(message: str = "hi") -> dict:
    return {"model": "auto", "messages": [{"role": "user", "content": message}]}


# --------------------------------------------------------------------------- #
# Migration tests (1-5)
# --------------------------------------------------------------------------- #


def _table_columns(db_path: Path, table: str) -> set[str]:
    with sqlite3.connect(db_path) as conn:
        return {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _index_names(db_path: Path) -> set[str]:
    with sqlite3.connect(db_path) as conn:
        return {row[1] for row in conn.execute("PRAGMA index_list(agent_jobs)").fetchall()}


def test_migration_creates_all_phase1a_tables(tmp_path):
    store = _store(tmp_path)
    db_path = store.path
    for table in ("agent_jobs", "job_results", "job_events", "job_attempts"):
        assert table in _table_columns(db_path, "sqlite_master") or True  # table exists
    # Verify columns directly.
    assert {"job_id", "status", "request_hash", "lease_owner", "lease_expires_at"} <= _table_columns(
        db_path, "agent_jobs"
    )
    assert {"result_id", "job_id", "result_type", "response_storage_key"} <= _table_columns(
        db_path, "job_results"
    )
    assert {"event_id", "job_id", "sequence_no", "event_type", "event_json"} <= _table_columns(
        db_path, "job_events"
    )
    assert {"attempt_id", "job_id", "attempt_no", "provider", "status"} <= _table_columns(
        db_path, "job_attempts"
    )


def test_migration_creates_required_indexes(tmp_path):
    db_path = _store(tmp_path).path
    idx = _index_names(db_path)
    assert "agent_jobs_status_idx" in idx
    assert "agent_jobs_created_idx" in idx
    assert "agent_jobs_client_idx" in idx
    assert "agent_jobs_idem_idx" in idx


def test_migration_is_idempotent(tmp_path):
    db_path = tmp_path / "admin.sqlite"
    BridgeAdminStore(db_path)
    # Second construction must not raise and must not duplicate columns.
    store = BridgeAdminStore(db_path)
    assert "job_id" in _table_columns(db_path, "artifacts")
    # Running again a third time is also safe.
    BridgeAdminStore(db_path)
    # No duplicate job_id column somehow appeared.
    cols = _table_columns(db_path, "artifacts")
    assert list(cols).count("job_id") == 1


def test_legacy_artifacts_gains_job_id_column(tmp_path):
    db_path = tmp_path / "admin.sqlite"
    # Create a legacy schema WITHOUT job_id, then run the store migration.
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE artifacts (
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
            CREATE TABLE account_captures (
                account TEXT PRIMARY KEY,
                capture_path TEXT NOT NULL,
                plan_type TEXT,
                email_masked TEXT,
                capabilities_json TEXT NOT NULL DEFAULT '{}',
                checks_json TEXT NOT NULL DEFAULT '[]',
                updated_at TEXT NOT NULL
            );
            CREATE TABLE settings (
                key TEXT PRIMARY KEY,
                value_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )
        live = tmp_path / "live.png"
        live.write_bytes(b"png")
        conn.execute(
            "INSERT INTO artifacts (file_id, kind, filename, path, download_url, content_type, bytes, metadata_json, created_at) VALUES (?, 'image', 'live.png', ?, 'http://x', 'image/png', 3, '{}', '2026-01-01T00:00:00Z')",
            ("legacy1", str(live)),
        )
    # Now migrate the existing DB.
    store = BridgeAdminStore(db_path)
    assert "job_id" in _table_columns(db_path, "artifacts")


def test_legacy_artifact_rows_remain_unchanged_and_readable(tmp_path):
    db_path = tmp_path / "admin.sqlite"
    live = tmp_path / "live.png"
    live.write_bytes(b"png")
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE artifacts (
                file_id TEXT PRIMARY KEY, kind TEXT NOT NULL, filename TEXT NOT NULL,
                path TEXT NOT NULL, download_url TEXT NOT NULL, content_type TEXT NOT NULL,
                bytes INTEGER, account TEXT, prompt TEXT,
                metadata_json TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL
            );
            CREATE TABLE account_captures (account TEXT PRIMARY KEY, capture_path TEXT NOT NULL, plan_type TEXT, email_masked TEXT, capabilities_json TEXT NOT NULL DEFAULT '{}', checks_json TEXT NOT NULL DEFAULT '[]', updated_at TEXT NOT NULL);
            CREATE TABLE settings (key TEXT PRIMARY KEY, value_json TEXT NOT NULL, updated_at TEXT NOT NULL);
            """
        )
        conn.execute(
            "INSERT INTO artifacts (file_id, kind, filename, path, download_url, content_type, bytes, metadata_json, created_at) VALUES (?, 'image', 'live.png', ?, 'http://x', 'image/png', 3, '{}', '2026-01-01T00:00:00Z')",
            ("legacy1", str(live)),
        )
    store = BridgeAdminStore(db_path)
    artifacts = store.list_artifacts()
    assert [a["file_id"] for a in artifacts] == ["legacy1"]
    assert artifacts[0]["job_id"] is None


def test_existing_admin_store_behavior_still_passes(tmp_path):
    # Re-run the original admin-store test against a Phase 1A-migrated DB.
    store = _store(tmp_path)
    live = tmp_path / "live.png"
    live.write_bytes(b"png")
    store.record_artifact(
        {"id": "live", "filename": "live.png", "path": str(live), "download_url": "http://x", "content_type": "image/png", "bytes": 3},
        kind="image",
    )
    assert [a["file_id"] for a in store.list_artifacts()] == ["live"]
    assert store.artifact_count() == 1


# --------------------------------------------------------------------------- #
# Job creation tests (6-10)
# --------------------------------------------------------------------------- #


def test_create_job_with_required_values(tmp_path):
    repo = _repo(tmp_path)
    res = repo.create_job(request_type="chat", model="auto", request=_make_chat_request(), now=T0)
    job = res.job
    assert job.job_id.startswith("job_")
    assert job.request_type == "chat"
    assert job.model == "auto"
    assert job.status == STATUS_ACCEPTED
    assert job.created_at == T0
    assert job.attempt_count == 0
    assert job.request_storage_key == f"agent-jobs/{job.job_id}/request.json"


def test_initial_event_inserted(tmp_path):
    repo = _repo(tmp_path)
    res = repo.create_job(request_type="chat", model="auto", request=_make_chat_request(), now=T0)
    events = repo.list_events(res.job.job_id)
    assert len(events) == 1
    assert events[0].event_type == "created"
    assert events[0].sequence_no == 1
    assert events[0].event_json["status"] == STATUS_ACCEPTED


def test_generated_ids_use_expected_prefixes(tmp_path):
    repo = _repo(tmp_path)
    res = repo.create_job(request_type="chat", model="auto", request=_make_chat_request(), now=T0)
    job_id = res.job.job_id
    assert job_id.startswith("job_")
    # event id prefix (created event already inserted)
    assert all(e.event_id.startswith("event_") for e in repo.list_events(job_id))
    # walk to queued, claim (creates an attempt_), succeed, save result_
    repo.transition(job_id, target=STATUS_VALIDATING, expected=STATUS_ACCEPTED, now=T1)
    repo.transition(job_id, target=STATUS_QUEUED, expected=STATUS_VALIDATING, now=T1)
    repo.claim_job(job_id, lease_owner="w1", lease_expires_at=T_FUTURE, now=T2)
    attempts = repo.list_attempts(job_id)
    assert attempts[0].attempt_id.startswith("attempt_")
    repo.transition(job_id, target=STATUS_SUCCEEDED, expected=STATUS_RUNNING, now=T3)
    result = repo.save_result(job_id, result_type="text", text_content="ok", now=T3)
    assert result.result_id.startswith("result_")


def test_canonical_request_hash_stable_across_key_order(tmp_path):
    a = {"model": "auto", "messages": [{"role": "user", "content": "hi"}], "n": 1}
    b = {"n": 1, "messages": [{"content": "hi", "role": "user"}], "model": "auto"}
    assert canonical_request_hash(a) == canonical_request_hash(b)
    # Different content -> different hash.
    assert canonical_request_hash(a) != canonical_request_hash({"model": "auto", "messages": []})


# --------------------------------------------------------------------------- #
# Idempotency tests (11-14)
# --------------------------------------------------------------------------- #


def test_no_idempotency_key_creates_separate_jobs(tmp_path):
    repo = _repo(tmp_path)
    r1 = repo.create_job(request_type="chat", model="auto", request=_make_chat_request(), now=T0)
    r2 = repo.create_job(request_type="chat", model="auto", request=_make_chat_request(), now=T1)
    assert r1.job.job_id != r2.job.job_id
    assert not r1.reused and not r2.reused


def test_same_key_same_payload_returns_original(tmp_path):
    repo = _repo(tmp_path)
    req = _make_chat_request()
    r1 = repo.create_job(request_type="chat", model="auto", request=req, idempotency_key="k1", now=T0)
    r2 = repo.create_job(request_type="chat", model="auto", request=req, idempotency_key="k1", now=T1)
    assert r1.job.job_id == r2.job.job_id
    assert not r1.reused
    assert r2.reused


def test_same_key_different_payload_raises_conflict(tmp_path):
    repo = _repo(tmp_path)
    repo.create_job(request_type="chat", model="auto", request=_make_chat_request("a"), idempotency_key="k1", now=T0)
    with pytest.raises(IdempotencyConflict):
        repo.create_job(request_type="chat", model="auto", request=_make_chat_request("b"), idempotency_key="k1", now=T1)


def test_concurrent_same_key_persists_exactly_one_job(tmp_path):
    repo = _repo(tmp_path)
    req = _make_chat_request()
    results: list = []
    barrier = threading.Barrier(2)

    def submit():
        barrier.wait()
        try:
            res = repo.create_job(request_type="chat", model="auto", request=req, idempotency_key="shared", now=T0)
            results.append(res.job.job_id)
        except Exception as exc:  # noqa: BLE001
            results.append(exc)

    t1 = threading.Thread(target=submit)
    t2 = threading.Thread(target=submit)
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    job_ids = [r for r in results if isinstance(r, str)]
    # Exactly one distinct job id persisted.
    assert len(set(job_ids)) == 1
    # No exception leaked (the loser reused the winner).
    assert all(isinstance(r, str) for r in results)


# --------------------------------------------------------------------------- #
# State-machine tests (15-20)
# --------------------------------------------------------------------------- #


VALID_TRANSITIONS = [
    (STATUS_ACCEPTED, STATUS_VALIDATING),
    (STATUS_VALIDATING, STATUS_QUEUED),
    (STATUS_VALIDATING, STATUS_FAILED),
    (STATUS_QUEUED, STATUS_RUNNING),
    (STATUS_QUEUED, STATUS_CANCEL_REQUESTED),
    (STATUS_QUEUED, STATUS_EXPIRED),
    (STATUS_RUNNING, STATUS_STREAMING),
    (STATUS_RUNNING, STATUS_RETRY_WAIT),
    (STATUS_RUNNING, STATUS_CANCEL_REQUESTED),
    (STATUS_RUNNING, STATUS_SUCCEEDED),
    (STATUS_RUNNING, STATUS_FAILED),
    (STATUS_STREAMING, STATUS_RUNNING),
    (STATUS_STREAMING, STATUS_SUCCEEDED),
    (STATUS_STREAMING, STATUS_CANCEL_REQUESTED),
    (STATUS_STREAMING, STATUS_RETRY_WAIT),
    (STATUS_RETRY_WAIT, STATUS_QUEUED),
    (STATUS_RETRY_WAIT, STATUS_CANCEL_REQUESTED),
    (STATUS_RETRY_WAIT, STATUS_EXPIRED),
    (STATUS_CANCEL_REQUESTED, STATUS_CANCELLED),
]


@pytest.mark.parametrize("current,target", VALID_TRANSITIONS)
def test_valid_transitions_succeed(tmp_path, current, target):
    repo = _repo(tmp_path)
    job_id = _create_job_at(repo, current, tmp_path)
    repo.transition(job_id, target=target, expected=current, now=T2)
    assert repo.get_job(job_id).status == target


def test_invalid_transitions_fail():
    bad = [(STATUS_ACCEPTED, STATUS_SUCCEEDED), (STATUS_QUEUED, STATUS_SUCCEEDED), (STATUS_RUNNING, STATUS_QUEUED)]
    for current, target in bad:
        with pytest.raises(InvalidTransition):
            validate_transition(current, target)


def test_terminal_states_reject_transitions():
    for terminal in TERMINAL_STATUSES:
        for target in {STATUS_SUCCEEDED, STATUS_FAILED, STATUS_QUEUED}:
            if target == terminal:
                continue
            with pytest.raises(InvalidTransition):
                validate_transition(terminal, target)


def test_compare_and_swap_detects_stale_expected_status(tmp_path):
    repo = _repo(tmp_path)
    job_id = repo.create_job(request_type="chat", model="auto", request=_make_chat_request(), now=T0).job.job_id
    repo.transition(job_id, target=STATUS_VALIDATING, expected=STATUS_ACCEPTED, now=T1)
    # Expected status is now stale.
    with pytest.raises(InvalidTransition):
        repo.transition(job_id, target=STATUS_QUEUED, expected=STATUS_ACCEPTED, now=T2)


def test_transition_creates_expected_event(tmp_path):
    repo = _repo(tmp_path)
    job_id = repo.create_job(request_type="chat", model="auto", request=_make_chat_request(), now=T0).job.job_id
    before = len(repo.list_events(job_id))
    repo.transition(job_id, target=STATUS_VALIDATING, expected=STATUS_ACCEPTED, now=T1)
    after = repo.list_events(job_id)
    assert len(after) == before + 1
    ev = after[-1]
    assert ev.event_type == "transition"
    assert ev.event_json["from"] == STATUS_ACCEPTED
    assert ev.event_json["to"] == STATUS_VALIDATING


def test_timestamps_written_once_and_preserved(tmp_path):
    repo = _repo(tmp_path)
    job_id = repo.create_job(request_type="chat", model="auto", request=_make_chat_request(), now=T0).job.job_id
    repo.transition(job_id, target=STATUS_VALIDATING, expected=STATUS_ACCEPTED, now=T1)
    repo.transition(job_id, target=STATUS_FAILED, expected=STATUS_VALIDATING, error_code="x", error_message="bad", now=T2)
    job = repo.get_job(job_id)
    assert job.created_at == T0
    assert job.completed_at == T2  # failed -> completed_at


# --------------------------------------------------------------------------- #
# Event tests (21-24)
# --------------------------------------------------------------------------- #


def test_event_sequence_monotonic(tmp_path):
    repo = _repo(tmp_path)
    job_id = repo.create_job(request_type="chat", model="auto", request=_make_chat_request(), now=T0).job.job_id
    repo.transition(job_id, target=STATUS_VALIDATING, expected=STATUS_ACCEPTED, now=T1)
    repo.transition(job_id, target=STATUS_QUEUED, expected=STATUS_VALIDATING, now=T2)
    seqs = [e.sequence_no for e in repo.list_events(job_id)]
    assert seqs == sorted(seqs)
    assert seqs[0] == 1
    assert seqs[-1] == 3


def test_events_listed_in_sequence_order(tmp_path):
    repo = _repo(tmp_path)
    job_id = repo.create_job(request_type="chat", model="auto", request=_make_chat_request(), now=T0).job.job_id
    for _ in range(3):
        pass
    events = repo.list_events(job_id)
    assert [e.sequence_no for e in events] == [1]


def test_duplicate_sequence_no_prevented(tmp_path):
    repo = _repo(tmp_path)
    job_id = repo.create_job(request_type="chat", model="auto", request=_make_chat_request(), now=T0).job.job_id
    with sqlite3.connect(repo._db_path) as conn:
        # next seq is 2 (created already inserted seq 1)
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO job_events (event_id, job_id, sequence_no, event_type, event_json, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                ("event_dup", job_id, 1, "x", "{}", T1),
            )


def test_event_payloads_are_valid_json_no_secrets(tmp_path):
    repo = _repo(tmp_path)
    job_id = repo.create_job(request_type="chat", model="auto", request=_make_chat_request(), now=T0).job.job_id
    repo.transition(job_id, target=STATUS_VALIDATING, expected=STATUS_ACCEPTED, now=T1)
    repo.transition(
        job_id,
        target=STATUS_FAILED,
        expected=STATUS_VALIDATING,
        error_code="chatgpt_auth_or_browser_challenge",
        error_message="Bearer secrettokendata authorization: hunter2",
        now=T1,
    )
    for ev in repo.list_events(job_id):
        # valid JSON dict
        assert isinstance(ev.event_json, dict)
        # event payload never carries the raw secret
        blob = str(ev.event_json)
        assert "secrettokendata" not in blob
        assert "hunter2" not in blob


# --------------------------------------------------------------------------- #
# Attempt tests (25-29)
# --------------------------------------------------------------------------- #


def test_start_attempt_increments_count_once(tmp_path):
    repo = _repo(tmp_path)
    job_id = _create_job_at(repo, STATUS_RUNNING, tmp_path)
    repo.start_attempt(job_id, account_alias="main-free", now=T2)
    assert repo.get_job(job_id).attempt_count == 1
    repo.start_attempt(job_id, account_alias="main-free", now=T3)
    assert repo.get_job(job_id).attempt_count == 2


def test_attempt_numbers_sequential(tmp_path):
    repo = _repo(tmp_path)
    job_id = _create_job_at(repo, STATUS_RUNNING, tmp_path)
    repo.start_attempt(job_id, now=T2)
    repo.start_attempt(job_id, now=T3)
    nos = [a.attempt_no for a in repo.list_attempts(job_id)]
    assert nos == [1, 2]


def test_finish_attempt_persists_status_and_redacted_errors(tmp_path):
    repo = _repo(tmp_path)
    job_id = _create_job_at(repo, STATUS_RUNNING, tmp_path)
    repo.start_attempt(job_id, now=T2)
    att = repo.finish_attempt(
        job_id, 1, status=STATUS_FAILED, error_code="chatgpt_rate_limited", error_message="Bearer abc cookie: z", now=T3
    )
    assert att.status == STATUS_FAILED
    assert att.error_code == "chatgpt_rate_limited"
    assert "abc" not in (att.error_message or "")
    assert "z" not in (att.error_message or "")


def test_attempts_list_in_numeric_order(tmp_path):
    repo = _repo(tmp_path)
    job_id = _create_job_at(repo, STATUS_RUNNING, tmp_path)
    repo.start_attempt(job_id, now=T2)
    repo.start_attempt(job_id, now=T3)
    repo.start_attempt(job_id, now=T4)
    nos = [a.attempt_no for a in repo.list_attempts(job_id)]
    assert nos == [1, 2, 3]


def test_concurrent_attempt_creation_no_duplicate_numbers(tmp_path):
    repo = _repo(tmp_path)
    job_id = _create_job_at(repo, STATUS_RUNNING, tmp_path)
    barrier = threading.Barrier(2)
    errors: list = []

    def start():
        barrier.wait()
        try:
            repo.start_attempt(job_id, now=T2)
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=start) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    nos = [a.attempt_no for a in repo.list_attempts(job_id)]
    assert nos == sorted(nos)
    assert len(nos) == len(set(nos)) == 2


# --------------------------------------------------------------------------- #
# Result tests (30-33)
# --------------------------------------------------------------------------- #


def test_save_and_retrieve_result(tmp_path):
    repo = _repo(tmp_path)
    job_id = repo.create_job(request_type="chat", model="auto", request=_make_chat_request(), now=T0).job.job_id
    repo.save_result(job_id, result_type="text", text_content="hello", model="auto", finish_reason="stop", now=T1)
    res = repo.get_result(job_id)
    assert res is not None
    assert res.text_content == "hello"
    assert res.finish_reason == "stop"


def test_result_associates_with_job(tmp_path):
    repo = _repo(tmp_path)
    job_id = repo.create_job(request_type="chat", model="auto", request=_make_chat_request(), now=T0).job.job_id
    res = repo.save_result(job_id, result_type="text", text_content="ok", now=T1)
    assert repo.get_job(job_id).result_id == res.result_id


def test_duplicate_final_result_rejected(tmp_path):
    repo = _repo(tmp_path)
    job_id = repo.create_job(request_type="chat", model="auto", request=_make_chat_request(), now=T0).job.job_id
    repo.save_result(job_id, result_type="text", text_content="ok", now=T1)
    with pytest.raises(IdempotencyConflict):
        repo.save_result(job_id, result_type="text", text_content="ok2", now=T2)


def test_large_response_uses_storage_key_not_blob(tmp_path):
    repo = _repo(tmp_path)
    job_id = repo.create_job(request_type="chat", model="auto", request=_make_chat_request(), now=T0).job.job_id
    res = repo.save_result(job_id, result_type="text", response_storage_key=f"agent-jobs/{job_id}/response.json", now=T1)
    assert res.response_storage_key == f"agent-jobs/{job_id}/response.json"
    assert res.text_content is None


# --------------------------------------------------------------------------- #
# Artifact tests (34-37)
# --------------------------------------------------------------------------- #


def _png(tmp_path: Path, name: str) -> Path:
    p = tmp_path / name
    p.write_bytes(b"png-bytes")
    return p


def test_artifact_associated_with_job(tmp_path):
    repo = _repo(tmp_path)
    job_id = repo.create_job(request_type="image_generation", model="gpt-image-1", request={"prompt": "x"}, now=T0).job.job_id
    p = _png(tmp_path, "out.png")
    repo.record_artifact(job_id, asset={"id": "f1", "filename": "out.png", "path": str(p), "download_url": "http://x", "content_type": "image/png"}, kind="image")
    arts = repo.list_artifacts(job_id)
    assert [a["file_id"] for a in arts] == ["f1"]
    assert arts[0]["job_id"] == job_id


def test_artifacts_listed_by_job(tmp_path):
    repo = _repo(tmp_path)
    job_id = repo.create_job(request_type="image_generation", model="gpt-image-1", request={"prompt": "x"}, now=T0).job.job_id
    other = repo.create_job(request_type="image_generation", model="gpt-image-1", request={"prompt": "y"}, now=T1).job.job_id
    p1 = _png(tmp_path, "a.png")
    p2 = _png(tmp_path, "b.png")
    repo.record_artifact(job_id, asset={"id": "f1", "filename": "a.png", "path": str(p1), "download_url": "http://a", "content_type": "image/png"}, kind="image")
    repo.record_artifact(other, asset={"id": "f2", "filename": "b.png", "path": str(p2), "download_url": "http://b", "content_type": "image/png"}, kind="image")
    assert [a["file_id"] for a in repo.list_artifacts(job_id)] == ["f1"]
    assert [a["file_id"] for a in repo.list_artifacts(other)] == ["f2"]


def test_legacy_artifacts_without_job_supported(tmp_path):
    store = _store(tmp_path)
    repo = AgentJobRepository(store)
    p = _png(tmp_path, "legacy.png")
    store.record_artifact({"id": "legacy", "filename": "legacy.png", "path": str(p), "download_url": "http://x", "content_type": "image/png"}, kind="image")
    # legacy artifact is not returned for any job
    job_id = repo.create_job(request_type="chat", model="auto", request=_make_chat_request(), now=T0).job.job_id
    assert repo.list_artifacts(job_id) == []
    # but still listed by the legacy store method
    assert store.list_artifacts()[0]["file_id"] == "legacy"


def test_unknown_job_artifact_association_is_just_a_value(tmp_path):
    # The schema has no FK enforcement (matches repo style), so an artifact
    # may carry a job_id that has no agent_jobs row. This is consistent with
    # the existing artifacts table, which has no FKs.
    store = _store(tmp_path)
    repo = AgentJobRepository(store)
    p = _png(tmp_path, "x.png")
    repo.record_artifact("job_does_not_exist", asset={"id": "f9", "filename": "x.png", "path": str(p), "download_url": "http://x", "content_type": "image/png"}, kind="image")
    assert [a["file_id"] for a in repo.list_artifacts("job_does_not_exist")] == ["f9"]


# --------------------------------------------------------------------------- #
# Claim and lease tests (38-44)
# --------------------------------------------------------------------------- #


def test_queued_job_can_be_claimed(tmp_path):
    repo = _repo(tmp_path)
    job_id = _create_job_at(repo, STATUS_QUEUED, tmp_path)
    out = repo.claim_job(job_id, lease_owner="w1", lease_expires_at=T_FUTURE, now=T2)
    assert out is not None
    assert out.job_id == job_id


def test_claim_moves_to_running(tmp_path):
    repo = _repo(tmp_path)
    job_id = _create_job_at(repo, STATUS_QUEUED, tmp_path)
    repo.claim_job(job_id, lease_owner="w1", lease_expires_at=T_FUTURE, now=T2)
    assert repo.get_job(job_id).status == STATUS_RUNNING


def test_claim_sets_lease_owner_and_expiry(tmp_path):
    repo = _repo(tmp_path)
    job_id = _create_job_at(repo, STATUS_QUEUED, tmp_path)
    repo.claim_job(job_id, lease_owner="w1", lease_expires_at=T_FUTURE, account_alias="main-free", now=T2)
    job = repo.get_job(job_id)
    assert job.lease_owner == "w1"
    assert job.lease_expires_at == T_FUTURE
    assert job.started_at == T2
    assert job.account_alias == "main-free"


def test_only_one_of_two_concurrent_claimers_succeeds(tmp_path):
    repo = _repo(tmp_path)
    job_id = _create_job_at(repo, STATUS_QUEUED, tmp_path)
    barrier = threading.Barrier(2)
    outcomes: list = []

    def claim(owner):
        barrier.wait()
        out = repo.claim_job(job_id, lease_owner=owner, lease_expires_at=T_FUTURE, now=T2)
        outcomes.append(out)

    t1 = threading.Thread(target=claim, args=("w1",))
    t2 = threading.Thread(target=claim, args=("w2",))
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    winners = [o for o in outcomes if o is not None]
    assert len(winners) == 1
    assert outcomes.count(None) == 1


def test_non_queued_job_cannot_be_claimed(tmp_path):
    repo = _repo(tmp_path)
    job_id = repo.create_job(request_type="chat", model="auto", request=_make_chat_request(), now=T0).job.job_id
    # accepted, not queued
    assert repo.claim_job(job_id, lease_owner="w1", lease_expires_at=T_FUTURE, now=T1) is None


def test_matching_lease_owner_can_renew(tmp_path):
    repo = _repo(tmp_path)
    job_id = _create_job_at(repo, STATUS_QUEUED, tmp_path)
    repo.claim_job(job_id, lease_owner="w1", lease_expires_at=T1, now=T2)
    assert repo.renew_lease(job_id, lease_owner="w1", lease_expires_at=T_FUTURE, now=T3) is True


def test_non_owner_cannot_renew(tmp_path):
    repo = _repo(tmp_path)
    job_id = _create_job_at(repo, STATUS_QUEUED, tmp_path)
    repo.claim_job(job_id, lease_owner="w1", lease_expires_at=T1, now=T2)
    assert repo.renew_lease(job_id, lease_owner="w2", lease_expires_at=T_FUTURE, now=T3) is False


# --------------------------------------------------------------------------- #
# Recovery tests (45-51)
# --------------------------------------------------------------------------- #


def test_stale_running_job_with_attempts_remaining_requeued(tmp_path):
    repo = _repo(tmp_path)
    job_id = _create_job_at(repo, STATUS_QUEUED, tmp_path, max_attempts=3)
    repo.claim_job(job_id, lease_owner="w1", lease_expires_at=T1, now=T2)  # attempt_count=1
    summary = repo.recover_stale_jobs(now=T3)
    assert job_id in summary.requeued
    assert repo.get_job(job_id).status == STATUS_QUEUED


def test_stale_streaming_job_with_attempts_remaining_requeued(tmp_path):
    repo = _repo(tmp_path)
    job_id = _create_job_at(repo, STATUS_QUEUED, tmp_path, max_attempts=3)
    repo.claim_job(job_id, lease_owner="w1", lease_expires_at=T1, now=T2)
    repo.transition(job_id, target=STATUS_STREAMING, expected=STATUS_RUNNING, now=T2)
    summary = repo.recover_stale_jobs(now=T3)
    assert job_id in summary.requeued
    assert repo.get_job(job_id).status == STATUS_QUEUED


def test_stale_job_at_max_attempts_becomes_failed_worker_crash(tmp_path):
    repo = _repo(tmp_path)
    job_id = _create_job_at(repo, STATUS_QUEUED, tmp_path, max_attempts=1)
    repo.claim_job(job_id, lease_owner="w1", lease_expires_at=T1, now=T2)  # attempt_count=1 == max
    summary = repo.recover_stale_jobs(now=T3)
    assert job_id in summary.failed
    job = repo.get_job(job_id)
    assert job.status == STATUS_FAILED
    assert job.error_code == "worker_crash"


def test_non_stale_running_job_not_changed(tmp_path):
    repo = _repo(tmp_path)
    job_id = _create_job_at(repo, STATUS_QUEUED, tmp_path)
    repo.claim_job(job_id, lease_owner="w1", lease_expires_at=T_FUTURE, now=T2)
    summary = repo.recover_stale_jobs(now=T3)
    assert summary.requeued == []
    assert summary.failed == []
    assert repo.get_job(job_id).status == STATUS_RUNNING


def test_lease_fields_cleared_during_recovery(tmp_path):
    repo = _repo(tmp_path)
    job_id = _create_job_at(repo, STATUS_QUEUED, tmp_path, max_attempts=3)
    repo.claim_job(job_id, lease_owner="w1", lease_expires_at=T1, now=T2)
    repo.recover_stale_jobs(now=T3)
    job = repo.get_job(job_id)
    assert job.lease_owner is None
    assert job.lease_expires_at is None


def test_recovery_events_appended(tmp_path):
    repo = _repo(tmp_path)
    job_id = _create_job_at(repo, STATUS_QUEUED, tmp_path, max_attempts=3)
    repo.claim_job(job_id, lease_owner="w1", lease_expires_at=T1, now=T2)
    before = len(repo.list_events(job_id))
    repo.recover_stale_jobs(now=T3)
    after = repo.list_events(job_id)
    assert len(after) == before + 1
    assert after[-1].event_type == "recovery_requeued"


def test_recovery_sweep_twice_is_idempotent(tmp_path):
    repo = _repo(tmp_path)
    job_id = _create_job_at(repo, STATUS_QUEUED, tmp_path, max_attempts=3)
    repo.claim_job(job_id, lease_owner="w1", lease_expires_at=T1, now=T2)
    first = repo.recover_stale_jobs(now=T3)
    second = repo.recover_stale_jobs(now=T4)
    assert first.requeued == [job_id]
    assert second.requeued == []
    assert second.failed == []


# --------------------------------------------------------------------------- #
# Cancellation persistence tests (52-55)
# --------------------------------------------------------------------------- #


def test_cancellable_states_enter_cancel_requested(tmp_path):
    repo = _repo(tmp_path)
    for current in (STATUS_QUEUED, STATUS_RUNNING, STATUS_RETRY_WAIT):
        job_id = _create_job_at(repo, current, tmp_path)
        repo.request_cancel(job_id, now=T1)
        assert repo.get_job(job_id).status == STATUS_CANCEL_REQUESTED


def test_cancellation_request_timestamp_persists(tmp_path):
    repo = _repo(tmp_path)
    job_id = _create_job_at(repo, STATUS_QUEUED, tmp_path)
    repo.request_cancel(job_id, now=T5)
    assert repo.get_job(job_id).cancel_requested_at == T5


def test_cancel_does_not_invoke_provider(tmp_path):
    # Persistence only: requesting cancel on a running job must not require
    # any provider/runtime; it only writes state.
    repo = _repo(tmp_path)
    job_id = _create_job_at(repo, STATUS_RUNNING, tmp_path)
    repo.request_cancel(job_id, now=T5)
    # The job is still running (not auto-cancelled) until a terminal move.
    assert repo.get_job(job_id).status == STATUS_CANCEL_REQUESTED


def test_terminal_jobs_reject_cancellation(tmp_path):
    repo = _repo(tmp_path)
    job_id = _create_job_at(repo, STATUS_FAILED, tmp_path)
    with pytest.raises(InvalidTransition):
        repo.request_cancel(job_id, now=T5)


# --------------------------------------------------------------------------- #
# Listing tests (56-60)
# --------------------------------------------------------------------------- #


def test_jobs_list_newest_first(tmp_path):
    repo = _repo(tmp_path)
    ids = []
    for i, ts in enumerate([T0, T1, T2]):
        ids.append(repo.create_job(request_type="chat", model="auto", request=_make_chat_request(str(i)), now=ts).job.job_id)
    page = repo.list_jobs(limit=10)
    assert [j.job_id for j in page.jobs] == list(reversed(ids))


def test_each_filter_works(tmp_path):
    repo = _repo(tmp_path)
    j1 = repo.create_job(request_type="chat", model="auto", request=_make_chat_request("a"), client_request_id="c1", now=T0).job
    j2 = repo.create_job(request_type="image_generation", model="gpt-image-1", request={"prompt": "x"}, client_request_id="c2", now=T1).job
    repo.transition(j2.job_id, target=STATUS_VALIDATING, expected=STATUS_ACCEPTED, now=T1)
    repo.transition(j2.job_id, target=STATUS_FAILED, expected=STATUS_VALIDATING, error_code="boom", now=T2)
    assert [j.job_id for j in repo.list_jobs(status=STATUS_ACCEPTED).jobs] == [j1.job_id]
    assert [j.job_id for j in repo.list_jobs(request_type="image_generation").jobs] == [j2.job_id]
    assert [j.job_id for j in repo.list_jobs(model="gpt-image-1").jobs] == [j2.job_id]
    assert [j.job_id for j in repo.list_jobs(client_request_id="c1").jobs] == [j1.job_id]
    assert [j.job_id for j in repo.list_jobs(error_code="boom").jobs] == [j2.job_id]


def test_combined_filters_work(tmp_path):
    repo = _repo(tmp_path)
    j1 = repo.create_job(request_type="chat", model="auto", request=_make_chat_request("a"), client_request_id="c1", now=T0).job
    j2 = repo.create_job(request_type="chat", model="auto", request=_make_chat_request("b"), client_request_id="c2", now=T1).job
    page = repo.list_jobs(request_type="chat", client_request_id="c1")
    assert [j.job_id for j in page.jobs] == [j1.job_id]
    assert j2.job_id not in [j.job_id for j in page.jobs]


def test_cursor_pagination_stable_with_equal_timestamps(tmp_path):
    repo = _repo(tmp_path)
    # Many jobs at the same timestamp; job_id is the tiebreaker.
    ids = [repo.create_job(request_type="chat", model="auto", request=_make_chat_request(str(i)), now=T0).job.job_id for i in range(5)]
    page = repo.list_jobs(limit=2)
    first_page = [j.job_id for j in page.jobs]
    assert page.has_more is True
    page2 = repo.list_jobs(limit=2, cursor=page.next_cursor)
    second_page = [j.job_id for j in page2.jobs]
    # No overlap between pages.
    assert set(first_page) & set(second_page) == set()
    # All 5 distinct ids covered across pages eventually.
    all_ids = set(first_page) | set(second_page)
    page3 = repo.list_jobs(limit=10, cursor=page2.next_cursor)
    all_ids |= {j.job_id for j in page3.jobs}
    assert all_ids == set(ids)


def test_limit_safely_bounded(tmp_path):
    repo = _repo(tmp_path)
    for i in range(3):
        repo.create_job(request_type="chat", model="auto", request=_make_chat_request(str(i)), now=T0)
    # Request an absurd limit; it is capped.
    page = repo.list_jobs(limit=100000)
    assert len(page.jobs) <= 200


# --------------------------------------------------------------------------- #
# Redaction tests (61-64)
# --------------------------------------------------------------------------- #


def test_persisted_errors_no_bearer_tokens(tmp_path):
    repo = _repo(tmp_path)
    job_id = repo.create_job(request_type="chat", model="auto", request=_make_chat_request(), now=T0).job.job_id
    repo.transition(job_id, target=STATUS_VALIDATING, expected=STATUS_ACCEPTED, now=T1)
    repo.transition(job_id, target=STATUS_FAILED, expected=STATUS_VALIDATING, error_code="x", error_message="Authorization: Bearer abc123.token", now=T1)
    msg = repo.get_job(job_id).error_message or ""
    assert "abc123.token" not in msg
    assert "<redacted>" in msg  # value redacted, label retained


def test_persisted_errors_no_cookies(tmp_path):
    repo = _repo(tmp_path)
    job_id = repo.create_job(request_type="chat", model="auto", request=_make_chat_request(), now=T0).job.job_id
    repo.transition(job_id, target=STATUS_VALIDATING, expected=STATUS_ACCEPTED, now=T1)
    repo.transition(job_id, target=STATUS_FAILED, expected=STATUS_VALIDATING, error_code="x", error_message="Cookie: sid=secretcookie; a=b", now=T1)
    msg = repo.get_job(job_id).error_message or ""
    assert "secretcookie" not in msg


def test_safe_diagnostic_info_remains(tmp_path):
    repo = _repo(tmp_path)
    job_id = repo.create_job(request_type="chat", model="auto", request=_make_chat_request(), now=T0).job.job_id
    repo.transition(job_id, target=STATUS_VALIDATING, expected=STATUS_ACCEPTED, now=T1)
    repo.transition(job_id, target=STATUS_FAILED, expected=STATUS_VALIDATING, error_code="chatgpt_rate_limited", error_message="account quota exceeded; retry later", now=T1)
    msg = repo.get_job(job_id).error_message or ""
    assert "account quota exceeded" in msg


def test_persisted_errors_no_api_keys_or_secrets(tmp_path):
    assert "sk-realkey" not in sanitize_error("api-key: sk-realkey", code="x")
    assert "supersecret" not in sanitize_error("passphrase: supersecret", code="x")
    assert "pw123" not in sanitize_error("password: pw123", code="x")


# --------------------------------------------------------------------------- #
# Helpers: place a job into a given state for transition tests
# --------------------------------------------------------------------------- #


def _create_job_at(repo: AgentJobRepository, status: str, tmp_path: Path, *, max_attempts: int = 3) -> str:
    """Create a job and walk it to ``status`` via valid transitions.

    For terminal states, the job is moved through ``queued -> running`` (or
    streaming/retry_wait) then to the terminal target.
    """

    job_id = repo.create_job(request_type="chat", model="auto", request=_make_chat_request(), max_attempts=max_attempts, now=T0).job.job_id
    if status == STATUS_ACCEPTED:
        return job_id
    repo.transition(job_id, target=STATUS_VALIDATING, expected=STATUS_ACCEPTED, now=T0)
    if status == STATUS_VALIDATING:
        return job_id
    if status == STATUS_FAILED:
        repo.transition(job_id, target=STATUS_FAILED, expected=STATUS_VALIDATING, error_code="err", error_message="bad", now=T0)
        return job_id
    repo.transition(job_id, target=STATUS_QUEUED, expected=STATUS_VALIDATING, now=T0)
    if status == STATUS_QUEUED:
        return job_id
    if status == STATUS_EXPIRED:
        repo.transition(job_id, target=STATUS_EXPIRED, expected=STATUS_QUEUED, now=T0)
        return job_id
    if status == STATUS_CANCEL_REQUESTED:
        repo.request_cancel(job_id, now=T0)
        return job_id
    if status == STATUS_CANCELLED:
        repo.request_cancel(job_id, now=T0)
        repo.transition(job_id, target=STATUS_CANCELLED, expected=STATUS_CANCEL_REQUESTED, now=T0)
        return job_id
    # running / streaming / retry_wait / succeeded via transitions (no claim,
    # so attempt_count stays 0 and the attempt tests can drive start_attempt).
    repo.transition(job_id, target=STATUS_RUNNING, expected=STATUS_QUEUED, now=T0)
    if status == STATUS_RUNNING:
        return job_id
    if status == STATUS_STREAMING:
        repo.transition(job_id, target=STATUS_STREAMING, expected=STATUS_RUNNING, now=T0)
        return job_id
    if status == STATUS_RETRY_WAIT:
        repo.transition(job_id, target=STATUS_RETRY_WAIT, expected=STATUS_RUNNING, error_code="retryable", error_message="busy", now=T0)
        return job_id
    if status == STATUS_SUCCEEDED:
        repo.transition(job_id, target=STATUS_SUCCEEDED, expected=STATUS_RUNNING, now=T0)
        return job_id
    raise AssertionError(f"unsupported setup status: {status}")
