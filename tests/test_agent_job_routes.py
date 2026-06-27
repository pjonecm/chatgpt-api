"""Phase 1B Agent Job route-service + HTTP integration tests.

Synthetic only: no network, captures, provider calls, ChatGPT calls, Docker,
Bun, or external services. Proves the non-execution boundary with spies.
"""

from __future__ import annotations

import http.client
import json
import threading
from http.server import HTTPServer
from pathlib import Path

import pytest

import chatgpt_api.api.openai_compat as compat
from chatgpt_api.api.agent_job_routes import (
    AgentJobRouteService,
    SUPPORTED_JOB_TYPES,
    normalize_request,
    serialize_artifact,
    serialize_event,
    serialize_result,
    serialize_status,
    serialize_submission,
    write_request_json,
)
from chatgpt_api.api.agent_jobs import (
    AgentJobRepository,
    STATUS_CANCELLED,
    STATUS_CANCEL_REQUESTED,
    STATUS_FAILED,
    STATUS_QUEUED,
)
from chatgpt_api.api.admin_store import BridgeAdminStore
from chatgpt_api.api.openai_compat import OpenAICompatConfig
from chatgpt_api.api.text_execution import write_response_json

T0 = "2026-01-01T00:00:00Z"


def _svc(tmp_path: Path) -> tuple[AgentJobRouteService, AgentJobRepository, Path]:
    store = BridgeAdminStore(tmp_path / "admin.sqlite")
    repo = AgentJobRepository(store)
    output_root = tmp_path / "agent-jobs"
    return AgentJobRouteService(repo, output_root), repo, output_root


def _chat_body(message: str = "hi", **extra) -> dict:
    body = {"type": "chat", "model": "auto", "messages": [{"role": "user", "content": message}]}
    body.update(extra)
    return body


def _research_body(message: str = "research agi", **extra) -> dict:
    body = {
        "type": "deep_research",
        "model": "chatgpt-deep-research",
        "messages": [{"role": "user", "content": message}],
    }
    body.update(extra)
    return body


# --------------------------------------------------------------------------- #
# Route-service: normalization (1-3)
# --------------------------------------------------------------------------- #


def test_valid_chat_request_normalization():
    normalized, job_type, max_attempts, expires_at, body_idem = normalize_request(
        {"type": "chat", "model": "auto", "messages": [{"role": "user", "content": "hi"}], "max_attempts": 2}
    )
    assert job_type == "chat"
    assert max_attempts == 2
    assert normalized["model"] == "auto"
    assert normalized["messages"] == [{"role": "user", "content": "hi"}]
    assert "idempotency_key" not in normalized  # transport metadata stripped


def test_valid_deep_research_request_normalization():
    normalized, job_type, max_attempts, _, _ = normalize_request(_research_body())
    assert job_type == "deep_research"
    assert normalized["model"] == "chatgpt-deep-research"
    assert "stream" not in normalized


def test_unsupported_job_types_rejected():
    for bad in ("image_generation", "image_edit", "vision"):
        with pytest.raises(Exception) as exc:
            normalize_request({"type": bad, "model": "x", "messages": [{"role": "user", "content": "y"}]})
        assert "unsupported_job_type" in str(exc.value) or exc.value.code == "unsupported_job_type"  # noqa: PT012


# --------------------------------------------------------------------------- #
# Validation (4-10)
# --------------------------------------------------------------------------- #


def test_multimodal_content_rejected():
    with pytest.raises(Exception):
        normalize_request(
            {"type": "chat", "model": "auto", "messages": [{"role": "user", "content": [{"type": "text", "text": "x"}]}]}
        )


def test_empty_messages_rejected():
    with pytest.raises(Exception):
        normalize_request({"type": "chat", "model": "auto", "messages": []})


def test_invalid_roles_rejected():
    with pytest.raises(Exception):
        normalize_request({"type": "chat", "model": "auto", "messages": [{"role": "developer", "content": "x"}]})


def test_invalid_model_rejected():
    with pytest.raises(Exception):
        normalize_request({"type": "chat", "model": "", "messages": [{"role": "user", "content": "x"}]})


def test_invalid_max_attempts_rejected():
    with pytest.raises(Exception):
        normalize_request({"type": "chat", "model": "auto", "messages": [{"role": "user", "content": "x"}], "max_attempts": 0})
    with pytest.raises(Exception):
        normalize_request({"type": "chat", "model": "auto", "messages": [{"role": "user", "content": "x"}], "max_attempts": 99})


def test_invalid_expiry_rejected():
    with pytest.raises(Exception):
        normalize_request({"type": "chat", "model": "auto", "messages": [{"role": "user", "content": "x"}], "expires_at": "not-a-date"})


def test_unsupported_callback_rejected():
    with pytest.raises(Exception):
        normalize_request({**_chat_body(), "callback_url": "https://evil.example/hook"})


def test_deep_research_rejects_stream_and_temporary_chat():
    with pytest.raises(Exception):
        normalize_request({**_research_body(), "stream": True})
    with pytest.raises(Exception):
        normalize_request({**_research_body(), "temporary_chat": True})


# --------------------------------------------------------------------------- #
# Idempotency (11-15)
# --------------------------------------------------------------------------- #


def test_header_idempotency_key_overrides_body_key(tmp_path):
    svc, repo, _ = _svc(tmp_path)
    body = _chat_body(idempotency_key="body-key")
    status, payload = svc.submit(body, "header-key")
    assert status == 201
    job = repo.get_job(payload["job_id"])
    assert job.idempotency_key == "header-key"


def test_semantic_hash_stable_across_header_body_key_location(tmp_path):
    svc1, repo1, _ = _svc(tmp_path)
    # Key in body
    s1, p1 = svc1.submit(_chat_body(idempotency_key="K"), None)
    # Same request, key in header
    s2, p2 = svc1.submit(_chat_body(), "K")
    assert s1 == 201 and s2 == 200
    assert p1["job_id"] == p2["job_id"]


def test_new_submission_returns_created_result(tmp_path):
    svc, _, _ = _svc(tmp_path)
    status, payload = svc.submit(_chat_body(), None)
    assert status == 201
    assert payload["status"] == "queued"
    assert payload["job_id"].startswith("job_")


def test_matching_duplicate_returns_reused_result(tmp_path):
    svc, _, _ = _svc(tmp_path)
    body = _chat_body()
    s1, p1 = svc.submit(body, "K")
    s2, p2 = svc.submit(body, "K")
    assert s1 == 201 and s2 == 200
    assert p1["job_id"] == p2["job_id"]


def test_idempotency_conflict_maps_correctly(tmp_path):
    svc, _, _ = _svc(tmp_path)
    svc.submit(_chat_body("same"), "K")
    status, payload = svc.submit(_chat_body("different"), "K")
    assert status == 409
    assert payload["error"]["code"] == "idempotency_conflict"


# --------------------------------------------------------------------------- #
# Submission lifecycle (16-24)
# --------------------------------------------------------------------------- #


def test_new_job_reaches_queued(tmp_path):
    svc, repo, _ = _svc(tmp_path)
    s, p = svc.submit(_chat_body(), None)
    assert repo.get_job(p["job_id"]).status == STATUS_QUEUED


def test_events_include_created_validating_queued_progression(tmp_path):
    svc, repo, _ = _svc(tmp_path)
    s, p = svc.submit(_chat_body(), None)
    events = repo.list_events(p["job_id"])
    # created + transition(accepted->validating) + transition(validating->queued)
    assert events[0].event_type == "created"
    transition_events = [e for e in events if e.event_type == "transition"]
    assert len(transition_events) == 2
    targets = [e.event_json.get("to") for e in transition_events]
    assert "validating" in targets and "queued" in targets


def test_request_json_written_atomically(tmp_path):
    svc, _, output_root = _svc(tmp_path)
    s, p = svc.submit(_chat_body(), None)
    target = output_root / p["job_id"] / "request.json"
    assert target.exists()
    # no leftover temp file
    assert not list(target.parent.glob("*.tmp.*"))


def test_stored_json_contains_normalized_request_only(tmp_path):
    svc, _, output_root = _svc(tmp_path)
    s, p = svc.submit(_chat_body("hello"), None)
    stored = json.loads((output_root / p["job_id"] / "request.json").read_text())
    assert stored == {
        "type": "chat",
        "model": "auto",
        "messages": [{"role": "user", "content": "hello"}],
        "stream": False,
        "max_attempts": 3,
    }


def test_stored_json_contains_no_auth_headers_or_keys(tmp_path):
    svc, _, output_root = _svc(tmp_path)
    s, p = svc.submit(_chat_body(), "SECRET-KEY")
    stored = (output_root / p["job_id"] / "request.json").read_text()
    assert "SECRET-KEY" not in stored
    assert "authorization" not in stored.lower()
    assert "cookie" not in stored.lower()
    assert "idempotency_key" not in stored


def test_storage_failure_transitions_job_to_failed(tmp_path, monkeypatch):
    svc, repo, output_root = _svc(tmp_path)

    def boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr("chatgpt_api.api.agent_job_routes.write_request_json", boom)
    s, p = svc.submit(_chat_body(), None)
    assert s == 500
    assert p["error"]["code"] == "storage_failure"
    job = repo.get_job(p["job_id"])
    assert job.status == STATUS_FAILED
    assert job.error_code == "storage_failure"


def test_storage_failure_uses_redacted_error(tmp_path, monkeypatch):
    svc, repo, _ = _svc(tmp_path)

    def boom(*args, **kwargs):
        raise OSError("Authorization: Bearer supersecrettoken cookie: leaked")

    monkeypatch.setattr("chatgpt_api.api.agent_job_routes.write_request_json", boom)
    s, p = svc.submit(_chat_body(), None)
    job = repo.get_job(p["job_id"])
    msg = job.error_message or ""
    assert "supersecrettoken" not in msg
    assert "leaked" not in msg


def test_reused_request_does_not_create_duplicate_events(tmp_path):
    svc, repo, _ = _svc(tmp_path)
    body = _chat_body()
    svc.submit(body, "K")
    before = len(repo.list_events(repo.get_job_by_idempotency_key("K").job_id))
    svc.submit(body, "K")  # reuse
    after = len(repo.list_events(repo.get_job_by_idempotency_key("K").job_id))
    assert before == after


def test_reused_request_does_not_create_second_request_directory(tmp_path):
    svc, _, output_root = _svc(tmp_path)
    body = _chat_body()
    s1, p1 = svc.submit(body, "K")
    # corrupt or leave the file; reuse should not create a new dir
    svc.submit(body, "K")
    dirs = [d.name for d in (output_root).iterdir() if d.is_dir()]
    assert dirs == [p1["job_id"]]


# --------------------------------------------------------------------------- #
# Serializers (25-28)
# --------------------------------------------------------------------------- #


def test_safe_status_serializer_excludes_internal_fields(tmp_path):
    svc, repo, _ = _svc(tmp_path)
    s, p = svc.submit(_chat_body(), None)
    job = repo.get_job(p["job_id"])
    status = serialize_status(job, artifact_count=0)
    for forbidden in (
        "idempotency_key",
        "request_hash",
        "request_storage_key",
        "response_storage_key",
        "lease_owner",
        "lease_expires_at",
        "callback_url",
        "callback_status",
        "priority",
        "result_id",
    ):
        assert forbidden not in status
    assert status["result_available"] is False


def test_safe_result_serializer_excludes_storage_paths(tmp_path):
    svc, repo, _ = _svc(tmp_path)
    s, p = svc.submit(_chat_body(), None)
    repo.transition(p["job_id"], target="running", expected="queued")
    repo.transition(p["job_id"], target="succeeded", expected="running")
    repo.save_result(p["job_id"], result_type="text", text_content="answer", response_storage_key="agent-jobs/x/response.json")
    result = repo.get_result(p["job_id"])
    serialized = serialize_result(result)
    assert "response_storage_key" not in serialized
    assert serialized["text"] == "answer"
    assert "response" not in serialized


def test_safe_event_serializer_parses_json(tmp_path):
    svc, repo, _ = _svc(tmp_path)
    s, p = svc.submit(_chat_body(), None)
    event = repo.list_events(p["job_id"])[0]
    serialized = serialize_event(event)
    assert isinstance(serialized["data"], dict)
    assert serialized["data"]["status"] == "accepted"


def test_safe_artifact_serializer_excludes_file_paths(tmp_path):
    artifact = {
        "file_id": "file_1",
        "filename": "result.md",
        "path": "/secret/fs/path/result.md",
        "download_url": "http://host/v1/chatgpt/files/file_1/result.md",
        "content_type": "text/markdown",
        "bytes": 10,
        "created_at": T0,
        "job_id": "job_x",
        "account": "main",
        "prompt": "secret prompt",
    }
    serialized = serialize_artifact(artifact)
    assert "path" not in serialized
    assert "job_id" not in serialized
    assert "account" not in serialized
    assert "prompt" not in serialized
    assert serialized["download_url"] == "/v1/chatgpt/files/file_1/result.md"


# --------------------------------------------------------------------------- #
# Cancellation (29-31)
# --------------------------------------------------------------------------- #


def test_cancellation_stops_at_cancel_requested(tmp_path):
    svc, repo, _ = _svc(tmp_path)
    s, p = svc.submit(_chat_body(), None)
    status, payload = svc.cancel(p["job_id"])
    assert status == 200
    assert payload["status"] == STATUS_CANCEL_REQUESTED
    assert repo.get_job(p["job_id"]).status == STATUS_CANCEL_REQUESTED  # not cancelled


def test_cancellation_is_idempotent_when_already_requested(tmp_path):
    svc, _, _ = _svc(tmp_path)
    s, p = svc.submit(_chat_body(), None)
    svc.cancel(p["job_id"])
    status, payload = svc.cancel(p["job_id"])
    assert status == 200
    assert payload["status"] == STATUS_CANCEL_REQUESTED


def test_terminal_cancellation_raises_conflict(tmp_path):
    svc, repo, _ = _svc(tmp_path)
    s, p = svc.submit(_chat_body(), None)
    repo.transition(p["job_id"], target="expired", expected="queued")
    status, payload = svc.cancel(p["job_id"])
    assert status == 409
    assert payload["error"]["code"] == "cancel_conflict"


# --------------------------------------------------------------------------- #
# Non-execution boundary (32)
# --------------------------------------------------------------------------- #


def test_queued_jobs_are_never_claimed_or_executed(tmp_path):
    svc, repo, _ = _svc(tmp_path)
    s, p = svc.submit(_chat_body(), None)
    job = repo.get_job(p["job_id"])
    assert job.status == STATUS_QUEUED
    assert job.attempt_count == 0
    assert job.lease_owner is None
    assert job.started_at is None
    assert job.account_alias is None


# --------------------------------------------------------------------------- #
# HTTP integration (33-52)
# --------------------------------------------------------------------------- #


def _server(tmp_path: Path, api_key: str = "test-key"):
    cfg = OpenAICompatConfig(account="test", api_key=api_key, admin_db_path=tmp_path / "admin.sqlite")
    server = HTTPServer(("127.0.0.1", 0), compat._handler_class(cfg))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def _http(server, method, path, body=None, key="test-key", headers=None):
    conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
    h = {}
    if key:
        h["Authorization"] = f"Bearer {key}"
    if body is not None:
        h["Content-Type"] = "application/json"
    if headers:
        h.update(headers)
    conn.request(method, path, body=json.dumps(body) if body is not None else None, headers=h)
    resp = conn.getresponse()
    data = resp.read()
    ctype = resp.getheader("Content-Type")
    conn.close()
    return resp.status, (json.loads(data) if data and ctype and "json" in ctype else data), ctype


@pytest.fixture
def http_server(tmp_path):
    server, thread = _server(tmp_path)
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_post_returns_201_for_new_chat_job(http_server):
    status, payload, _ = _http(http_server, "POST", "/v1/agent/jobs", _chat_body())
    assert status == 201
    assert payload["status"] == "queued"


def test_duplicate_matching_submission_returns_200(http_server):
    _http(http_server, "POST", "/v1/agent/jobs", _chat_body(), headers={"Idempotency-Key": "K"})
    status, payload, _ = _http(http_server, "POST", "/v1/agent/jobs", _chat_body(), headers={"Idempotency-Key": "K"})
    assert status == 200


def test_duplicate_conflicting_submission_returns_409(http_server):
    _http(http_server, "POST", "/v1/agent/jobs", _chat_body("a"), headers={"Idempotency-Key": "K"})
    status, payload, _ = _http(http_server, "POST", "/v1/agent/jobs", _chat_body("b"), headers={"Idempotency-Key": "K"})
    assert status == 409
    assert payload["error"]["code"] == "idempotency_conflict"


def test_unsupported_type_returns_400(http_server):
    status, payload, _ = _http(
        http_server, "POST", "/v1/agent/jobs", {"type": "image_generation", "model": "gpt-image-1", "prompt": "x"}
    )
    assert status == 400
    assert payload["error"]["code"] == "unsupported_job_type"


def test_malformed_json_returns_400(http_server):
    conn = http.client.HTTPConnection("127.0.0.1", http_server.server_port, timeout=5)
    conn.request(
        "POST", "/v1/agent/jobs", body="{not json", headers={"Authorization": "Bearer test-key", "Content-Type": "application/json"}
    )
    resp = conn.getresponse()
    data = resp.read()
    conn.close()
    assert resp.status == 400
    assert json.loads(data)["error"]["type"] == "invalid_request_error"


def test_unauthorized_submission_returns_401_when_auth_configured(tmp_path):
    server, thread = _server(tmp_path, api_key="secret-key")
    try:
        status, _, _ = _http(server, "POST", "/v1/agent/jobs", _chat_body(), key=None)
        assert status == 401
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_get_jobs_returns_jobs(http_server):
    _http(http_server, "POST", "/v1/agent/jobs", _chat_body())
    status, payload, _ = _http(http_server, "GET", "/v1/agent/jobs")
    assert status == 200
    assert len(payload["jobs"]) >= 1


def test_list_filtering_works(http_server):
    _http(http_server, "POST", "/v1/agent/jobs", _chat_body())
    _http(http_server, "POST", "/v1/agent/jobs", _research_body())
    status, payload, _ = _http(http_server, "GET", "/v1/agent/jobs?type=chat")
    assert status == 200
    assert all(j["type"] == "chat" for j in payload["jobs"])
    assert len(payload["jobs"]) == 1


def test_cursor_pagination_is_stable(http_server):
    for i in range(5):
        _http(http_server, "POST", "/v1/agent/jobs", _chat_body(str(i)))
    _, page1, _ = _http(http_server, "GET", "/v1/agent/jobs?limit=2")
    assert page1["has_more"] is True
    _, page2, _ = _http(http_server, "GET", f"/v1/agent/jobs?limit=2&cursor={page1['next_cursor']}")
    ids1 = {j["job_id"] for j in page1["jobs"]}
    ids2 = {j["job_id"] for j in page2["jobs"]}
    assert ids1 & ids2 == set()


def test_get_job_returns_safe_status(http_server):
    _, p, _ = _http(http_server, "POST", "/v1/agent/jobs", _chat_body())
    status, payload, _ = _http(http_server, "GET", f"/v1/agent/jobs/{p['job_id']}")
    assert status == 200
    assert "lease_owner" not in payload
    assert "request_hash" not in payload


def test_unknown_status_route_returns_404(http_server):
    status, _, _ = _http(http_server, "GET", "/v1/agent/jobs/job_nope")
    assert status == 404


def test_result_for_queued_job_returns_409_pending(http_server):
    _, p, _ = _http(http_server, "POST", "/v1/agent/jobs", _chat_body())
    status, payload, _ = _http(http_server, "GET", f"/v1/agent/jobs/{p['job_id']}/result")
    assert status == 409
    assert payload["error"]["code"] == "pending"


def test_seeded_synthetic_result_returns_200(tmp_path):
    server, thread = _server(tmp_path)
    try:
        _, p, _ = _http(server, "POST", "/v1/agent/jobs", _chat_body())
        # seed a result directly through the repository
        store = BridgeAdminStore(tmp_path / "admin.sqlite")
        repo = AgentJobRepository(store)
        repo.transition(p["job_id"], target="running", expected="queued")
        response = {"id": "chatcmpl_test", "object": "chat.completion", "choices": [{"message": {"role": "assistant", "content": "answer"}}]}
        response_storage_key = write_response_json(tmp_path / "agent-jobs", p["job_id"], response)
        repo.complete_job_with_result(
            p["job_id"],
            result_type="text",
            text_content="answer",
            response_storage_key=response_storage_key,
            finish_reason="stop",
        )
        status, payload, _ = _http(server, "GET", f"/v1/agent/jobs/{p['job_id']}/result")
        assert status == 200
        assert payload["text"] == "answer"
        assert payload["response"] == response
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_result_route_returns_storage_failure_when_response_payload_is_missing(tmp_path):
    svc, repo, _ = _svc(tmp_path)
    _, created = svc.submit(_chat_body(), None)
    repo.transition(created["job_id"], target="running", expected="queued")
    repo.complete_job_with_result(
        created["job_id"],
        result_type="text",
        text_content="answer",
        response_storage_key=f"agent-jobs/{created['job_id']}/results/response.json",
        finish_reason="stop",
    )
    status, payload = svc.get_result(created["job_id"])
    assert status == 500
    assert payload["error"]["code"] == "storage_failure"


def test_events_endpoint_returns_json(http_server):
    _, p, _ = _http(http_server, "POST", "/v1/agent/jobs", _chat_body())
    status, payload, _ = _http(http_server, "GET", f"/v1/agent/jobs/{p['job_id']}/events")
    assert status == 200
    assert "events" in payload
    assert payload["events"][0]["event_type"] == "created"


def test_events_endpoint_is_not_sse(http_server):
    _, p, _ = _http(http_server, "POST", "/v1/agent/jobs", _chat_body())
    _, _, ctype = _http(http_server, "GET", f"/v1/agent/jobs/{p['job_id']}/events")
    assert ctype is not None
    assert "text/event-stream" not in ctype


def test_artifacts_endpoint_returns_empty_list(http_server):
    _, p, _ = _http(http_server, "POST", "/v1/agent/jobs", _chat_body())
    status, payload, _ = _http(http_server, "GET", f"/v1/agent/jobs/{p['job_id']}/artifacts")
    assert status == 200
    assert payload["artifacts"] == []


def test_seeded_artifact_is_returned_safely(tmp_path):
    server, thread = _server(tmp_path)
    try:
        _, p, _ = _http(server, "POST", "/v1/agent/jobs", _chat_body())
        store = BridgeAdminStore(tmp_path / "admin.sqlite")
        repo = AgentJobRepository(store)
        art_file = tmp_path / "report.md"
        art_file.write_bytes(b"# report")
        repo.record_artifact(
            p["job_id"],
            asset={"id": "file_1", "filename": "report.md", "path": str(art_file), "download_url": "http://x", "content_type": "text/markdown", "bytes": 8},
            kind="research",
        )
        status, payload, _ = _http(server, "GET", f"/v1/agent/jobs/{p['job_id']}/artifacts")
        assert status == 200
        assert payload["artifacts"][0]["file_id"] == "file_1"
        assert "path" not in payload["artifacts"][0]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_cancel_endpoint_returns_cancel_requested(http_server):
    _, p, _ = _http(http_server, "POST", "/v1/agent/jobs", _chat_body())
    status, payload, _ = _http(http_server, "POST", f"/v1/agent/jobs/{p['job_id']}/cancel")
    assert status == 200
    assert payload["status"] == "cancel_requested"


def test_terminal_cancel_returns_409(tmp_path):
    server, thread = _server(tmp_path)
    try:
        _, p, _ = _http(server, "POST", "/v1/agent/jobs", _chat_body())
        store = BridgeAdminStore(tmp_path / "admin.sqlite")
        repo = AgentJobRepository(store)
        repo.transition(p["job_id"], target="expired", expected="queued")
        status, payload, _ = _http(server, "POST", f"/v1/agent/jobs/{p['job_id']}/cancel")
        assert status == 409
        assert payload["error"]["code"] == "cancel_conflict"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_existing_synchronous_routes_remain_unchanged(http_server):
    # /health and /v1/models must still work and be unchanged.
    status, _, _ = _http(http_server, "GET", "/health")
    assert status == 200
    status, _, _ = _http(http_server, "GET", "/v1/models")
    assert status == 200


# --------------------------------------------------------------------------- #
# Non-execution boundary spies (53-56)
# --------------------------------------------------------------------------- #


def test_provider_is_never_invoked(tmp_path, monkeypatch):
    """A chat job submission must not touch ChatGPTProvider."""

    called = []

    class _SpyProvider:
        def __init__(self, *a, **k):
            called.append("init")

        def __getattr__(self, name):
            def _stub(*a, **k):
                called.append(name)
                raise AssertionError(f"provider.{name} was invoked")

            return _stub

    monkeypatch.setattr("chatgpt_api.api.openai_compat.ChatGPTProvider", _SpyProvider)
    server, thread = _server(tmp_path)
    try:
        status, _, _ = _http(server, "POST", "/v1/agent/jobs", _chat_body())
        assert status == 201
        assert called == []
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_account_router_is_never_invoked_for_agent_routes(tmp_path, monkeypatch):
    """Agent routes must not select accounts."""

    original_init = compat.AccountRouter.__init__

    def _spy_init(self, *a, **k):
        raise AssertionError("AccountRouter was constructed during an agent route")

    monkeypatch.setattr(compat.AccountRouter, "order", lambda *a, **k: (_ for _ in ()).throw(AssertionError("router.order called")))
    server, thread = _server(tmp_path)
    try:
        status, _, _ = _http(server, "POST", "/v1/agent/jobs", _chat_body())
        assert status == 201
        status, _, _ = _http(server, "GET", "/v1/agent/jobs")
        assert status == 200
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        monkeypatch.setattr(compat.AccountRouter, "__init__", original_init)


def test_concurrency_limiter_code_is_never_invoked(tmp_path, monkeypatch):
    """The BoundedSemaphore-based limiters must not be touched."""

    import threading as _t

    sem_init = _t.BoundedSemaphore.__init__

    def _spy_sem(self, *a, **k):
        # Allow construction but record it; agent routes should not acquire.
        sem_init(self, *a, **k)

    monkeypatch.setattr(_t.BoundedSemaphore, "acquire", lambda *a, **k: (_ for _ in ()).throw(AssertionError("limiter acquired")))
    server, thread = _server(tmp_path)
    try:
        status, _, _ = _http(server, "POST", "/v1/agent/jobs", _chat_body())
        assert status == 201
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        monkeypatch.setattr(_t.BoundedSemaphore, "acquire", lambda self, *a, **k: True)


def test_no_background_thread_is_started(tmp_path):
    before = threading.active_count()
    server, thread = _server(tmp_path)
    try:
        _http(server, "POST", "/v1/agent/jobs", _chat_body())
        _http(server, "GET", "/v1/agent/jobs")
        # only the server's own serve_forever thread may have been added
        after = threading.active_count()
        assert after - before <= 1
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
