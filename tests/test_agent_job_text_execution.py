from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from chatgpt_api.api.config import OpenAICompatConfig
from chatgpt_api.api.text_execution import (
    TextExecutionResult,
    TextExecutionRuntime,
    TextExecutionStorageError,
    add_utc_seconds,
    execute_non_streaming_chat,
    load_request_json,
    load_response_json,
    request_file_path,
    resolve_storage_path,
    retry_backoff_seconds,
    write_response_json,
)


def test_request_and_response_storage_round_trip(tmp_path: Path):
    output_root = tmp_path / "agent-jobs"
    request_path = request_file_path(output_root, "job_123")
    request_path.parent.mkdir(parents=True, exist_ok=True)
    request_path.write_text('{"type":"chat","model":"auto","messages":[]}', encoding="utf-8")

    assert load_request_json(output_root, "job_123")["model"] == "auto"

    response = {"id": "chatcmpl_x", "choices": [{"message": {"content": "ok"}}]}
    storage_key = write_response_json(output_root, "job_123", response)
    assert load_response_json(tmp_path, storage_key) == response


def test_storage_path_rejects_traversal(tmp_path: Path):
    with pytest.raises(TextExecutionStorageError):
        resolve_storage_path(tmp_path, "../secrets.txt")


def test_load_request_rejects_non_object_json(tmp_path: Path):
    output_root = tmp_path / "agent-jobs"
    request_path = request_file_path(output_root, "job_123")
    request_path.parent.mkdir(parents=True, exist_ok=True)
    request_path.write_text("[]", encoding="utf-8")

    with pytest.raises(TextExecutionStorageError):
        load_request_json(output_root, "job_123")


def test_retry_helpers_are_deterministic():
    assert retry_backoff_seconds(1) == 5
    assert retry_backoff_seconds(2) == 10
    assert retry_backoff_seconds(6) == 160
    assert add_utc_seconds("2026-01-01T00:00:00Z", 15) == "2026-01-01T00:00:15Z"


def _runtime(non_agent_text: str = "plain reply", agent_text: str = "tool reply") -> TextExecutionRuntime:
    async def collect_messages(*args, **kwargs):
        return "acct", object(), non_agent_text

    async def collect_prompt_with_accounts(*args, **kwargs):
        return "acct", object(), agent_text

    async def collect_prompt(*args, **kwargs):
        return agent_text

    async def noop_retry(*args, **kwargs):
        return args[4], args[5]

    async def init_meta(*args, **kwargs):
        return {}

    return TextExecutionRuntime(
        str_or_none=lambda value: value if isinstance(value, str) else None,
        split_model_agent_mode=lambda model: (model, None),
        resolve_agent_prompt_mode=lambda config, body, mode: "optimized",
        resolve_model_alias=lambda model, effort: (model, effort),
        resolve_temporary_chat_mode=lambda config, body: False,
        router_for_request=lambda config, router, body: router,
        should_use_agent_bridge=lambda body, tools, mode: bool(tools),
        collect_messages_text_with_accounts=collect_messages,
        collect_prompt_text_with_accounts=collect_prompt_with_accounts,
        collect_prompt_text=collect_prompt,
        conversation_init_metadata=init_meta,
        build_chat_prompt=lambda messages, tools, tool_choice, prompt_mode: "prompt",
        build_missing_tool_retry_prompt=lambda prompt, invalid: prompt,
        parse_tool_calls=lambda text, tools: [{"id": "call_1"}] if text == agent_text and tools else [],
        filter_repeated_successful_tool_calls=lambda tool_calls, messages: tool_calls,
        retry_tool_policy_issues=noop_retry,
        retry_low_quality_tool_calls=noop_retry,
        should_retry_for_missing_tool_call=lambda messages, tools, tool_choice, text: False,
        has_successful_tool_result_after_latest_user=lambda messages: False,
        has_completed_file_action_after_latest_user=lambda messages: False,
        response_is_tool_call_json=lambda text: False,
        response_abandons_workspace_action=lambda text: False,
        completion_response=lambda requested_model, text, tool_calls, **kwargs: {
            "model": requested_model,
            "text": text,
            "tool_calls": tool_calls,
            **kwargs,
        },
        empty_response_error=lambda: RuntimeError("empty"),
        provider_error_type=RuntimeError,
        provider_error_factory=lambda *args, **kwargs: RuntimeError("provider"),
        model_fallback_for_config=lambda config, model: None,
        should_try_fallback_model=lambda exc: False,
        finish_chatgpt_operation=lambda operation_id: None,
    )


def test_execute_non_streaming_chat_plain_path_uses_shared_helper():
    result = asyncio.run(
        execute_non_streaming_chat(
            OpenAICompatConfig(account="test"),
            {"model": "auto", "messages": [{"role": "user", "content": "hi"}]},
            router=None,
            runtime=_runtime(non_agent_text="hello"),
        )
    )

    assert isinstance(result, TextExecutionResult)
    assert result.text == "hello"
    assert result.tool_calls == []
    assert result.finish_reason == "stop"


def test_execute_non_streaming_chat_agent_path_returns_tool_calls():
    result = asyncio.run(
        execute_non_streaming_chat(
            OpenAICompatConfig(account="test"),
            {
                "model": "auto",
                "messages": [{"role": "user", "content": "hi"}],
                "tools": [{"type": "function", "function": {"name": "demo"}}],
            },
            router=None,
            runtime=_runtime(agent_text="tool reply"),
        )
    )

    assert result.text == "tool reply"
    assert result.tool_calls == [{"id": "call_1"}]
    assert result.finish_reason == "tool_calls"
