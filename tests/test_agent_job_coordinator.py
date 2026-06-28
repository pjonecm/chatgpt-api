"""Synthetic tests for Phase 1C.2 Agent Job coordinator lifecycle."""

from __future__ import annotations

import threading
from pathlib import Path

import pytest

import chatgpt_api.api.openai_compat as compat
from chatgpt_api.api.admin_store import BridgeAdminStore
from chatgpt_api.api.agent_job_coordinator import AgentJobCoordinator
from chatgpt_api.api.agent_jobs import (
    AgentJobRepository,
    RecoverySummary,
    STATUS_ACCEPTED,
    STATUS_CANCELLED,
    STATUS_CANCEL_REQUESTED,
    STATUS_FAILED,
    STATUS_QUEUED,
    STATUS_RETRY_WAIT,
    STATUS_RUNNING,
    STATUS_VALIDATING,
)
from chatgpt_api.api.openai_compat import OpenAICompatConfig
from chatgpt_api.api.research_execution import ResearchExecutionResult
from chatgpt_api.api.text_execution import TextExecutionResult

T0 = "2026-01-01T00:00:00Z"
T1 = "2026-01-01T00:00:01Z"
T2 = "2026-01-01T00:00:02Z"
T3 = "2026-01-01T00:00:03Z"
T4 = "2026-01-01T00:00:04Z"
T_FUTURE = "2099-01-01T00:00:00Z"


def _store(tmp_path: Path) -> BridgeAdminStore:
    return BridgeAdminStore(tmp_path / "admin.sqlite")


def _repo(tmp_path: Path) -> AgentJobRepository:
    return AgentJobRepository(_store(tmp_path))


def _make_chat_request(message: str = "hi") -> dict:
    return {"model": "auto", "messages": [{"role": "user", "content": message}]}


def _queued_job(repo: AgentJobRepository, *, now: str = T0, message: str = "hi", max_attempts: int = 3) -> str:
    job_id = repo.create_job(
        request_type="chat",
        model="auto",
        request=_make_chat_request(message),
        max_attempts=max_attempts,
        now=now,
    ).job.job_id
    repo.transition(job_id, target=STATUS_VALIDATING, expected=STATUS_ACCEPTED, now=now)
    repo.transition(job_id, target=STATUS_QUEUED, expected=STATUS_VALIDATING, now=now)
    return job_id


def _queued_research_job(repo: AgentJobRepository, *, now: str = T0, message: str = "research") -> str:
    job_id = repo.create_job(
        request_type="deep_research",
        model="chatgpt-deep-research",
        request={
            "type": "deep_research",
            "model": "chatgpt-deep-research",
            "messages": [{"role": "user", "content": message}],
        },
        max_attempts=3,
        now=now,
    ).job.job_id
    repo.transition(job_id, target=STATUS_VALIDATING, expected=STATUS_ACCEPTED, now=now)
    repo.transition(job_id, target=STATUS_QUEUED, expected=STATUS_VALIDATING, now=now)
    return job_id


def _cancel_requested_job(repo: AgentJobRepository, current: str) -> str:
    if current == STATUS_ACCEPTED:
        job_id = repo.create_job(request_type="chat", model="auto", request=_make_chat_request(), now=T0).job.job_id
    elif current == STATUS_VALIDATING:
        job_id = repo.create_job(request_type="chat", model="auto", request=_make_chat_request(), now=T0).job.job_id
        repo.transition(job_id, target=STATUS_VALIDATING, expected=STATUS_ACCEPTED, now=T0)
    elif current == STATUS_QUEUED:
        job_id = _queued_job(repo)
    elif current == STATUS_RETRY_WAIT:
        job_id = _queued_job(repo)
        repo.claim_job(job_id, lease_owner="w1", lease_expires_at=T_FUTURE, now=T1)
        repo.schedule_retry(job_id, expected=STATUS_RUNNING, next_retry_at=T4, now=T2)
    else:
        raise AssertionError(f"unsupported setup status {current}")
    repo.request_cancel(job_id, now=T3)
    return job_id


def test_construction_does_not_start_thread(tmp_path):
    coordinator = AgentJobCoordinator(_repo(tmp_path))
    assert coordinator.thread is None


def test_start_creates_one_background_thread_and_is_idempotent(tmp_path):
    coordinator = AgentJobCoordinator(_repo(tmp_path), poll_interval_seconds=60)
    coordinator.start()
    first_thread = coordinator.thread
    assert first_thread is not None and first_thread.is_alive()
    coordinator.start()
    assert coordinator.thread is first_thread
    coordinator.stop()


def test_stop_is_idempotent(tmp_path):
    coordinator = AgentJobCoordinator(_repo(tmp_path), poll_interval_seconds=60)
    coordinator.stop()
    coordinator.start()
    thread = coordinator.thread
    coordinator.stop()
    assert thread is not None
    assert not thread.is_alive()
    coordinator.stop()


def test_wake_triggers_prompt_processing(tmp_path, monkeypatch):
    repo = _repo(tmp_path)
    coordinator = AgentJobCoordinator(repo, poll_interval_seconds=60)
    processed = threading.Event()
    original = repo.promote_due_retries

    def wrapped(*args, **kwargs):
        processed.set()
        return original(*args, **kwargs)

    monkeypatch.setattr(repo, "promote_due_retries", wrapped)
    coordinator.start()
    coordinator.wake()
    assert processed.wait(timeout=2)
    coordinator.stop()


def test_loop_exception_is_contained_and_later_cycle_runs(tmp_path, monkeypatch):
    repo = _repo(tmp_path)
    coordinator = AgentJobCoordinator(repo, poll_interval_seconds=60)
    processed = threading.Event()
    calls = {"count": 0}

    def flaky(*args, **kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError("boom")
        processed.set()
        return []

    monkeypatch.setattr(repo, "promote_due_retries", flaky)
    coordinator.start()
    coordinator.wake()
    for _ in range(50):
        if calls["count"] >= 1:
            break
        threading.Event().wait(0.01)
    coordinator.wake()
    assert processed.wait(timeout=2)
    coordinator.stop()
    assert calls["count"] >= 2


def test_startup_calls_recover_stale_jobs_once_before_executor(tmp_path, monkeypatch):
    repo = _repo(tmp_path)
    order: list[str] = []

    def recover(*, now=None):
        order.append("recover")
        return RecoverySummary()

    def execute(job):
        order.append(f"execute:{job.job_id}")

    monkeypatch.setattr(repo, "recover_stale_jobs", recover)
    _queued_job(repo)
    coordinator = AgentJobCoordinator(repo, poll_interval_seconds=60, executor=execute)
    coordinator.start()
    coordinator.wake()
    for _ in range(50):
        if len(order) >= 2:
            break
        threading.Event().wait(0.01)
    coordinator.stop()
    assert order[0] == "recover"
    assert order[1].startswith("execute:")


def test_startup_recovery_requeues_stale_running_job(tmp_path):
    repo = _repo(tmp_path)
    job_id = _queued_job(repo, max_attempts=3)
    repo.claim_job(job_id, lease_owner="w1", lease_expires_at=T1, now=T2)
    coordinator = AgentJobCoordinator(repo, poll_interval_seconds=60, now_fn=lambda: T3)
    coordinator.start()
    coordinator.stop()
    assert repo.get_job(job_id).status == STATUS_QUEUED


def test_startup_recovery_fails_stale_job_at_max_attempts(tmp_path):
    repo = _repo(tmp_path)
    job_id = _queued_job(repo, max_attempts=1)
    repo.claim_job(job_id, lease_owner="w1", lease_expires_at=T1, now=T2)
    coordinator = AgentJobCoordinator(repo, poll_interval_seconds=60, now_fn=lambda: T3)
    coordinator.start()
    coordinator.stop()
    job = repo.get_job(job_id)
    assert job.status == STATUS_FAILED
    assert job.error_code == "worker_crash"


def test_run_once_promotes_due_retries_but_not_future_retries(tmp_path):
    repo = _repo(tmp_path)
    due_job = _queued_job(repo, message="due")
    future_job = _queued_job(repo, message="future")
    repo.claim_job(due_job, lease_owner="w1", lease_expires_at=T_FUTURE, now=T1)
    repo.schedule_retry(due_job, expected=STATUS_RUNNING, next_retry_at=T2, now=T1)
    repo.claim_job(future_job, lease_owner="w2", lease_expires_at=T_FUTURE, now=T1)
    repo.schedule_retry(future_job, expected=STATUS_RUNNING, next_retry_at=T_FUTURE, now=T1)
    coordinator = AgentJobCoordinator(repo, now_fn=lambda: T3)
    result = coordinator.run_once()
    assert result.promoted_retry_ids == (due_job,)
    assert repo.get_job(due_job).status == STATUS_QUEUED
    assert repo.get_job(future_job).status == STATUS_RETRY_WAIT


def test_repeated_retry_polling_is_idempotent(tmp_path):
    repo = _repo(tmp_path)
    job_id = _queued_job(repo)
    repo.claim_job(job_id, lease_owner="w1", lease_expires_at=T_FUTURE, now=T1)
    repo.schedule_retry(job_id, expected=STATUS_RUNNING, next_retry_at=T2, now=T1)
    coordinator = AgentJobCoordinator(repo, now_fn=lambda: T3)
    first = coordinator.run_once()
    second = coordinator.run_once()
    assert first.promoted_retry_ids == (job_id,)
    assert second.promoted_retry_ids == ()


@pytest.mark.parametrize("current", [STATUS_ACCEPTED, STATUS_VALIDATING, STATUS_QUEUED, STATUS_RETRY_WAIT])
def test_non_running_cancellation_is_finalized_without_provider(tmp_path, current):
    repo = _repo(tmp_path)
    job_id = _cancel_requested_job(repo, current)
    coordinator = AgentJobCoordinator(repo, now_fn=lambda: T4)
    result = coordinator.run_once()
    assert result.cancelled_job_ids == (job_id,)
    job = repo.get_job(job_id)
    assert job.status == STATUS_CANCELLED
    assert job.cancelled_at == T4


def test_running_cancellation_is_not_finalized_in_phase_1c2(tmp_path):
    repo = _repo(tmp_path)
    job_id = _queued_job(repo)
    repo.claim_job(job_id, lease_owner="w1", lease_expires_at=T_FUTURE, now=T1)
    repo.request_cancel(job_id, now=T2)
    coordinator = AgentJobCoordinator(repo, now_fn=lambda: T3)
    result = coordinator.run_once()
    assert result.cancelled_job_ids == ()
    assert repo.get_job(job_id).status == STATUS_CANCEL_REQUESTED


def test_cancellation_finalization_is_idempotent_and_terminal_jobs_are_unchanged(tmp_path):
    repo = _repo(tmp_path)
    job_id = _cancel_requested_job(repo, STATUS_QUEUED)
    terminal_job = _queued_job(repo, message="terminal")
    repo.transition(terminal_job, target=STATUS_CANCEL_REQUESTED, expected=STATUS_QUEUED, now=T1)
    repo.transition(terminal_job, target=STATUS_CANCELLED, expected=STATUS_CANCEL_REQUESTED, now=T2)
    coordinator = AgentJobCoordinator(repo, now_fn=lambda: T4)
    first = coordinator.run_once()
    second = coordinator.run_once()
    assert first.cancelled_job_ids == (job_id,)
    assert second.cancelled_job_ids == ()
    assert repo.get_job(terminal_job).status == STATUS_CANCELLED


def test_two_coordinators_do_not_duplicate_cancellation_finalization(tmp_path):
    repo = _repo(tmp_path)
    job_id = _cancel_requested_job(repo, STATUS_QUEUED)
    coordinator1 = AgentJobCoordinator(repo, now_fn=lambda: T4)
    coordinator2 = AgentJobCoordinator(repo, now_fn=lambda: T4)
    results: list[tuple[str, ...]] = []
    barrier = threading.Barrier(2)

    def finalize(coordinator: AgentJobCoordinator):
        barrier.wait()
        results.append(coordinator.run_once().cancelled_job_ids)

    threads = [
        threading.Thread(target=finalize, args=(coordinator1,)),
        threading.Thread(target=finalize, args=(coordinator2,)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sum(job_id in cancelled for cancelled in results) == 1
    assert repo.get_job(job_id).status == STATUS_CANCELLED


def test_single_active_executor_boundary_leaves_second_job_queued(tmp_path):
    repo = _repo(tmp_path)
    first_job = _queued_job(repo, message="first")
    second_job = _queued_job(repo, message="second", now=T1)
    entered = threading.Event()
    release = threading.Event()
    started: list[str] = []

    def execute(job):
        started.append(job.job_id)
        claim = repo.claim_job(job.job_id, lease_owner=f"worker-{len(started)}", lease_expires_at=T_FUTURE, now=T2)
        assert claim is not None
        entered.set()
        release.wait(timeout=2)
        repo.transition(job.job_id, target=STATUS_FAILED, expected=STATUS_RUNNING, now=T3)

    coordinator = AgentJobCoordinator(repo, poll_interval_seconds=60, executor=execute)
    coordinator.start()
    coordinator.wake()
    assert entered.wait(timeout=2)
    assert started == [first_job]
    assert repo.get_job(second_job).status == STATUS_QUEUED
    release.set()
    coordinator.wake()
    for _ in range(50):
        if len(started) == 2:
            break
        threading.Event().wait(0.01)
    coordinator.stop()
    assert started == [first_job, second_job]


def test_coordinator_without_executor_does_not_claim_jobs(tmp_path):
    repo = _repo(tmp_path)
    job_id = _queued_job(repo)
    coordinator = AgentJobCoordinator(repo, now_fn=lambda: T3)
    result = coordinator.run_once()
    assert result.selected_job_id is None
    job = repo.get_job(job_id)
    assert job.status == STATUS_QUEUED
    assert job.attempt_count == 0


def test_run_once_selects_deep_research_jobs_for_executor(tmp_path):
    repo = _repo(tmp_path)
    job_id = _queued_research_job(repo)
    started: list[str] = []

    def execute(job):
        started.append(job.job_id)

    coordinator = AgentJobCoordinator(repo, now_fn=lambda: T3, executor=execute)
    result = coordinator.run_once()

    assert result.selected_job_id == job_id
    assert result.executor_invoked is True
    assert started == [job_id]


def test_create_server_installs_real_chat_executor_for_agent_jobs(tmp_path, monkeypatch):
    cfg = OpenAICompatConfig(account="test", api_key="test-key", admin_db_path=tmp_path / "admin.sqlite")
    server = compat.create_server(cfg)
    executed = threading.Event()

    async def fake_execute(config, body, router, runtime, *, operation_id=None, operation_extra=None):
        executed.set()
        return TextExecutionResult(
            response={
                "id": "chatcmpl_job",
                "object": "chat.completion",
                "choices": [{"index": 0, "message": {"role": "assistant", "content": "done"}, "finish_reason": "stop"}],
                "model": body["model"],
            },
            text="done",
            tool_calls=[],
            account="test",
            finish_reason="stop",
        )

    monkeypatch.setattr(compat, "execute_non_streaming_chat", fake_execute)

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        repo = AgentJobRepository(BridgeAdminStore(tmp_path / "admin.sqlite"))
        job_id = repo.create_job(
            request_type="chat",
            model="auto",
            request={"type": "chat", "model": "auto", "messages": [{"role": "user", "content": "hi"}]},
            max_attempts=3,
            now=T0,
        ).job.job_id
        repo.transition(job_id, target=STATUS_VALIDATING, expected=STATUS_ACCEPTED, now=T0)
        request_dir = tmp_path / "agent-jobs" / job_id
        request_dir.mkdir(parents=True, exist_ok=True)
        (request_dir / "request.json").write_text(
            '{"type":"chat","model":"auto","messages":[{"role":"user","content":"hi"}],"stream":false}',
            encoding="utf-8",
        )
        repo.transition(job_id, target=STATUS_QUEUED, expected=STATUS_VALIDATING, now=T1)
        server.agent_job_coordinator.wake()
        assert executed.wait(timeout=3)
        for _ in range(100):
            if repo.get_job(job_id).status == "succeeded":
                break
            threading.Event().wait(0.02)
        job = repo.get_job(job_id)
        assert job.status == "succeeded"
        assert job.result_id is not None
        result = repo.get_result(job_id)
        assert result is not None
        assert result.text_content == "done"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_create_server_executes_deep_research_agent_jobs(tmp_path, monkeypatch):
    cfg = OpenAICompatConfig(account="test", api_key="test-key", admin_db_path=tmp_path / "admin.sqlite")
    server = compat.create_server(cfg)
    executed = threading.Event()

    async def fake_execute(config, body, router, runtime, *, operation_id=None):
        executed.set()
        report_path = tmp_path / "report.md"
        report_path.write_text("# Research\n\nDone.", encoding="utf-8")
        return ResearchExecutionResult(
            requested_model=body["model"],
            model_slug="gpt-5-thinking",
            account="test",
            prompt=body["messages"][0]["content"],
            markdown="# Research\n\nDone.",
            report_path=report_path,
            metadata={"status": "complete"},
        )

    monkeypatch.setattr(compat, "execute_deep_research", fake_execute)

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        repo = AgentJobRepository(BridgeAdminStore(tmp_path / "admin.sqlite"))
        job_id = repo.create_job(
            request_type="deep_research",
            model="chatgpt-deep-research",
            request={
                "type": "deep_research",
                "model": "chatgpt-deep-research",
                "messages": [{"role": "user", "content": "research"}],
            },
            max_attempts=3,
            now=T0,
        ).job.job_id
        repo.transition(job_id, target=STATUS_VALIDATING, expected=STATUS_ACCEPTED, now=T0)
        request_dir = tmp_path / "agent-jobs" / job_id
        request_dir.mkdir(parents=True, exist_ok=True)
        (request_dir / "request.json").write_text(
            '{"type":"deep_research","model":"chatgpt-deep-research","messages":[{"role":"user","content":"research"}]}',
            encoding="utf-8",
        )
        repo.transition(job_id, target=STATUS_QUEUED, expected=STATUS_VALIDATING, now=T1)
        server.agent_job_coordinator.wake()
        assert executed.wait(timeout=3)
        for _ in range(100):
            if repo.get_job(job_id).status == "succeeded":
                break
            threading.Event().wait(0.02)
        job = repo.get_job(job_id)
        assert job.status == "succeeded"
        result = repo.get_result(job_id)
        assert result is not None
        assert result.result_type == "research"
        artifacts = repo.list_artifacts(job_id)
        assert artifacts[0]["content_type"].startswith("text/markdown")
        assert artifacts[0]["filename"] == "report.md"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_server_lifecycle_starts_and_stops_coordinator_once(tmp_path):
    repo = _repo(tmp_path)

    class SpyCoordinator(AgentJobCoordinator):
        def __init__(self):
            super().__init__(repo, poll_interval_seconds=60)
            self.start_calls = 0
            self.stop_calls = 0

        def start(self) -> None:
            self.start_calls += 1

        def stop(self) -> None:
            self.stop_calls += 1

    coordinator = SpyCoordinator()
    server = compat.create_server(
        OpenAICompatConfig(account="test", api_key="test-key", admin_db_path=tmp_path / "admin.sqlite"),
        coordinator=coordinator,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        for _ in range(50):
            if coordinator.start_calls:
                break
            threading.Event().wait(0.01)
        assert coordinator.start_calls == 1
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
    assert coordinator.stop_calls >= 1


def test_create_server_does_not_start_coordinator_until_serving(tmp_path):
    repo = _repo(tmp_path)

    class SpyCoordinator(AgentJobCoordinator):
        def __init__(self):
            super().__init__(repo, poll_interval_seconds=60)
            self.start_calls = 0

        def start(self) -> None:
            self.start_calls += 1

    coordinator = SpyCoordinator()
    server = compat.create_server(
        OpenAICompatConfig(account="test", api_key="test-key", admin_db_path=tmp_path / "admin.sqlite"),
        coordinator=coordinator,
    )
    try:
        assert coordinator.start_calls == 0
    finally:
        server.server_close()
