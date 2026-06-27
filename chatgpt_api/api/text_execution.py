"""Shared text execution helpers for synchronous chat and Agent Jobs.

This module owns the minimal reusable non-streaming text execution path used
by both ``POST /v1/chat/completions`` and the Agent Job coordinator's chat
executor. It also contains safe JSON storage helpers for persisted request and
response payloads plus small deterministic retry/backoff utilities.
"""

from __future__ import annotations

import json
import os
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path, PurePosixPath
from typing import Any

from chatgpt_api.api.config import OpenAICompatConfig

JsonObject = dict[str, Any]


class TextExecutionStorageError(RuntimeError):
    """Raised when a persisted request/response file is missing or unsafe."""


@dataclass(frozen=True, slots=True)
class TextExecutionResult:
    response: JsonObject
    text: str
    tool_calls: list[JsonObject]
    account: str | None
    finish_reason: str
    fallback_model: str | None = None


@dataclass(frozen=True, slots=True)
class TextExecutionRuntime:
    str_or_none: Callable[[Any], str | None]
    split_model_agent_mode: Callable[[str], tuple[str, str | None]]
    resolve_agent_prompt_mode: Callable[[OpenAICompatConfig, JsonObject, str | None], str]
    resolve_model_alias: Callable[[str, str | None], tuple[str, str | None]]
    resolve_temporary_chat_mode: Callable[[OpenAICompatConfig, JsonObject], bool]
    router_for_request: Callable[[OpenAICompatConfig, Any, JsonObject], Any]
    should_use_agent_bridge: Callable[[JsonObject, list[Any], str | None], bool]
    collect_messages_text_with_accounts: Callable[..., Awaitable[tuple[str, Any, str]]]
    collect_prompt_text_with_accounts: Callable[..., Awaitable[tuple[str, Any, str]]]
    collect_prompt_text: Callable[..., Awaitable[str]]
    conversation_init_metadata: Callable[[Any, str], Awaitable[JsonObject]]
    build_chat_prompt: Callable[[list[Any], list[Any], Any, str], str]
    build_missing_tool_retry_prompt: Callable[[str, str], str]
    parse_tool_calls: Callable[[str, list[Any]], list[JsonObject]]
    filter_repeated_successful_tool_calls: Callable[[list[JsonObject], list[Any]], list[JsonObject]]
    retry_tool_policy_issues: Callable[..., Awaitable[tuple[str, list[JsonObject]]]]
    retry_low_quality_tool_calls: Callable[..., Awaitable[tuple[str, list[JsonObject]]]]
    should_retry_for_missing_tool_call: Callable[[list[Any], list[Any], Any, str], bool]
    has_successful_tool_result_after_latest_user: Callable[[list[Any]], bool]
    has_completed_file_action_after_latest_user: Callable[[list[Any]], bool]
    response_is_tool_call_json: Callable[[str], bool]
    response_abandons_workspace_action: Callable[[str], bool]
    completion_response: Callable[..., JsonObject]
    empty_response_error: Callable[[], Exception]
    provider_error_type: type[Exception]
    provider_error_factory: Callable[..., Exception]
    model_fallback_for_config: Callable[[OpenAICompatConfig, str], str | None]
    should_try_fallback_model: Callable[[Exception], bool]
    finish_chatgpt_operation: Callable[[str | None], None]


def _json_dumps(data: JsonObject) -> bytes:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _write_json_atomic(path: Path, payload: JsonObject) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp.{os.getpid()}")
    try:
        with open(tmp, "wb") as handle:
            handle.write(_json_dumps(payload))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    except Exception:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass
        raise


def _read_json_object(path: Path) -> JsonObject:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise TextExecutionStorageError(f"missing persisted JSON file: {path.name}") from exc
    except json.JSONDecodeError as exc:
        raise TextExecutionStorageError(f"malformed persisted JSON file: {path.name}") from exc
    if not isinstance(payload, dict):
        raise TextExecutionStorageError(f"persisted JSON file must contain an object: {path.name}")
    return payload


def request_file_path(output_root: Path, job_id: str) -> Path:
    return output_root / job_id / "request.json"


def response_file_path(output_root: Path, job_id: str) -> Path:
    return output_root / job_id / "results" / "response.json"


def load_request_json(output_root: Path, job_id: str) -> JsonObject:
    return _read_json_object(request_file_path(output_root, job_id))


def write_response_json(output_root: Path, job_id: str, response: JsonObject) -> str:
    target = response_file_path(output_root, job_id)
    _write_json_atomic(target, response)
    return PurePosixPath("agent-jobs", job_id, "results", "response.json").as_posix()


def resolve_storage_path(storage_root: Path, storage_key: str) -> Path:
    posix_key = PurePosixPath(storage_key)
    if posix_key.is_absolute() or ".." in posix_key.parts or not posix_key.parts:
        raise TextExecutionStorageError("invalid storage key")
    root = storage_root.resolve()
    target = (root / Path(*posix_key.parts)).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise TextExecutionStorageError("storage key escapes the output directory") from exc
    return target


def load_response_json(storage_root: Path, storage_key: str) -> JsonObject:
    return _read_json_object(resolve_storage_path(storage_root, storage_key))


def retry_backoff_seconds(attempt_no: int) -> int:
    normalized = max(1, int(attempt_no))
    return min(300, 5 * (2 ** (normalized - 1)))


def add_utc_seconds(timestamp: str, seconds: int) -> str:
    dt = datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    return (dt + timedelta(seconds=max(0, int(seconds)))).strftime("%Y-%m-%dT%H:%M:%SZ")


def classify_retryable_error(status_code: int) -> bool:
    return status_code in {408, 409, 423, 425, 429} or status_code >= 500


async def execute_non_streaming_chat(
    config: OpenAICompatConfig,
    body: JsonObject,
    router: Any,
    runtime: TextExecutionRuntime,
    *,
    operation_id: str | None = None,
    operation_extra: JsonObject | None = None,
) -> TextExecutionResult:
    messages = body.get("messages")
    if not isinstance(messages, list):
        raise ValueError("messages must be a list")
    requested_model = runtime.str_or_none(body.get("model")) or "gpt-5-5"
    model, model_agent_mode = runtime.split_model_agent_mode(requested_model)
    agent_prompt_mode = runtime.resolve_agent_prompt_mode(config, body, model_agent_mode)
    model_slug, thinking_effort = runtime.resolve_model_alias(model, runtime.str_or_none(body.get("thinking_effort")))
    tools = body.get("tools") if isinstance(body.get("tools"), list) else []
    temporary_chat = runtime.resolve_temporary_chat_mode(config, body)
    router = runtime.router_for_request(config, router, body)
    extra = dict(operation_extra or {})

    try:
        if not runtime.should_use_agent_bridge(body, tools, model_agent_mode):
            account, provider, text = await runtime.collect_messages_text_with_accounts(
                config,
                router,
                messages,
                requested_model,
                model_slug,
                thinking_effort,
                temporary_chat,
                operation_id=operation_id,
            )
            if not text:
                raise runtime.provider_error_factory(
                    runtime.empty_response_error(),
                    requested_model,
                    model_slug,
                    await runtime.conversation_init_metadata(provider, model_slug),
                    account=account,
                )
            response = runtime.completion_response(requested_model, text, [], account=account, extra=extra)
            return TextExecutionResult(response=response, text=text, tool_calls=[], account=account, finish_reason="stop")

        prompt = runtime.build_chat_prompt(messages, tools, body.get("tool_choice"), agent_prompt_mode)
        fallback_model_used: str | None = None
        active_model_slug = model_slug
        active_thinking_effort = thinking_effort
        try:
            account, provider, text = await runtime.collect_prompt_text_with_accounts(
                config,
                router,
                prompt,
                requested_model,
                model_slug,
                thinking_effort,
                temporary_chat,
                operation_id=operation_id,
            )
        except runtime.provider_error_type as exc:
            fallback_model = runtime.model_fallback_for_config(config, model_slug)
            if fallback_model and runtime.should_try_fallback_model(exc):
                fallback_model_slug, fallback_effort = runtime.resolve_model_alias(fallback_model, None)
                account, provider, text = await runtime.collect_prompt_text_with_accounts(
                    config,
                    router,
                    prompt,
                    requested_model,
                    fallback_model_slug,
                    fallback_effort,
                    temporary_chat,
                    operation_id=operation_id,
                )
                active_model_slug = fallback_model_slug
                active_thinking_effort = fallback_effort
                fallback_model_used = fallback_model_slug
            else:
                raise
        if not text:
            if runtime.has_successful_tool_result_after_latest_user(messages) or runtime.has_completed_file_action_after_latest_user(messages):
                response = runtime.completion_response(
                    requested_model,
                    "Done.",
                    [],
                    account=account,
                    fallback_model=fallback_model_used,
                    extra=extra,
                )
                return TextExecutionResult(
                    response=response,
                    text="Done.",
                    tool_calls=[],
                    account=account,
                    finish_reason="stop",
                    fallback_model=fallback_model_used,
                )
            raise runtime.provider_error_factory(
                runtime.empty_response_error(),
                requested_model,
                active_model_slug,
                await runtime.conversation_init_metadata(provider, active_model_slug),
                account=account,
            )
        if runtime.has_completed_file_action_after_latest_user(messages) and (
            runtime.response_is_tool_call_json(text) or runtime.response_abandons_workspace_action(text)
        ):
            response = runtime.completion_response(
                requested_model,
                "Done.",
                [],
                account=account,
                fallback_model=fallback_model_used,
                extra=extra,
            )
            return TextExecutionResult(
                response=response,
                text="Done.",
                tool_calls=[],
                account=account,
                finish_reason="stop",
                fallback_model=fallback_model_used,
            )
        if runtime.has_successful_tool_result_after_latest_user(messages) and runtime.response_is_tool_call_json(text):
            response = runtime.completion_response(
                requested_model,
                "Done.",
                [],
                account=account,
                fallback_model=fallback_model_used,
                extra=extra,
            )
            return TextExecutionResult(
                response=response,
                text="Done.",
                tool_calls=[],
                account=account,
                finish_reason="stop",
                fallback_model=fallback_model_used,
            )
        tool_calls = runtime.filter_repeated_successful_tool_calls(runtime.parse_tool_calls(text, tools), messages)
        text, tool_calls = await runtime.retry_tool_policy_issues(
            provider,
            prompt,
            messages,
            tools,
            text,
            tool_calls,
            requested_model,
            active_model_slug,
            active_thinking_effort,
            temporary_chat,
        )
        text, tool_calls = await runtime.retry_low_quality_tool_calls(
            provider,
            prompt,
            messages,
            tools,
            text,
            tool_calls,
            requested_model,
            active_model_slug,
            active_thinking_effort,
            temporary_chat,
        )
        if not tool_calls and runtime.should_retry_for_missing_tool_call(messages, tools, body.get("tool_choice"), text):
            try:
                text = await runtime.collect_prompt_text(
                    provider,
                    runtime.build_missing_tool_retry_prompt(prompt, text),
                    active_model_slug,
                    active_thinking_effort,
                    temporary_chat,
                    operation_id=operation_id,
                )
            except Exception as exc:
                raise runtime.provider_error_factory(
                    exc,
                    requested_model,
                    active_model_slug,
                    await runtime.conversation_init_metadata(provider, active_model_slug),
                    account=account,
                ) from exc
            if not text:
                raise runtime.provider_error_factory(
                    runtime.empty_response_error(),
                    requested_model,
                    active_model_slug,
                    await runtime.conversation_init_metadata(provider, active_model_slug),
                    account=account,
                )
            tool_calls = runtime.filter_repeated_successful_tool_calls(runtime.parse_tool_calls(text, tools), messages)
            text, tool_calls = await runtime.retry_tool_policy_issues(
                provider,
                prompt,
                messages,
                tools,
                text,
                tool_calls,
                requested_model,
                active_model_slug,
                active_thinking_effort,
                temporary_chat,
            )
            text, tool_calls = await runtime.retry_low_quality_tool_calls(
                provider,
                prompt,
                messages,
                tools,
                text,
                tool_calls,
                requested_model,
                active_model_slug,
                active_thinking_effort,
                temporary_chat,
            )
        finish_reason = "tool_calls" if tool_calls else "stop"
        response = runtime.completion_response(
            requested_model,
            text,
            tool_calls,
            account=account,
            fallback_model=fallback_model_used,
            extra=extra,
        )
        return TextExecutionResult(
            response=response,
            text=text,
            tool_calls=tool_calls,
            account=account,
            finish_reason=finish_reason,
            fallback_model=fallback_model_used,
        )
    finally:
        runtime.finish_chatgpt_operation(operation_id)
