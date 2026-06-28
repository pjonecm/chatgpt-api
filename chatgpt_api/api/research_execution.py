"""Shared Deep Research execution helpers for sync HTTP and Agent Jobs."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from chatgpt_api.api.config import OpenAICompatConfig

JsonObject = dict[str, Any]


@dataclass(frozen=True, slots=True)
class ResearchExecutionResult:
    requested_model: str
    model_slug: str
    account: str
    prompt: str
    markdown: str
    report_path: Path
    metadata: JsonObject


@dataclass(frozen=True, slots=True)
class ResearchExecutionRuntime:
    str_or_none: Callable[[Any], str | None]
    request_is_deep_research: Callable[[JsonObject, str], bool]
    resolve_model_alias: Callable[[str, str | None], tuple[str, str | None]]
    latest_user_message_text: Callable[[list[Any]], str]
    latest_message_role: Callable[[list[Any]], str | None]
    collect_deep_research_with_accounts: Callable[..., Awaitable[tuple[str, Any, str, JsonObject]]]
    clean_deep_research_markdown: Callable[[str], str]
    save_deep_research_report: Callable[[OpenAICompatConfig, JsonObject, str, str], Path]
    empty_response_error: Callable[[], Exception]
    provider_error_factory: Callable[..., Exception]
    finish_chatgpt_operation: Callable[[str | None], None]


async def execute_deep_research(
    config: OpenAICompatConfig,
    body: JsonObject,
    router: Any,
    runtime: ResearchExecutionRuntime,
    *,
    operation_id: str | None,
    model_slug: str | None = None,
) -> ResearchExecutionResult | None:
    """Execute one synchronous Deep Research request without HTTP loopback.

    The caller owns operation creation, artifact registration, response
    serialization, and Agent Job lifecycle races. This helper owns the reused
    provider path and final markdown report extraction.
    """

    messages = body.get("messages")
    if not isinstance(messages, list):
        raise ValueError("messages must be a list")
    requested_model = runtime.str_or_none(body.get("model")) or "gpt-5-5"
    latest = runtime.latest_user_message_text(messages)
    if not latest or not runtime.request_is_deep_research(body, requested_model):
        return None
    if runtime.latest_message_role(messages) != "user":
        raise ValueError("Deep Research request already has follow-up messages in the transcript.")

    resolved_model_slug = model_slug
    if resolved_model_slug is None:
        resolved_model_slug, _ = runtime.resolve_model_alias(requested_model, None)
    try:
        account, provider, text, metadata = await runtime.collect_deep_research_with_accounts(
            config,
            router,
            latest,
            requested_model,
            resolved_model_slug,
            operation_id=operation_id,
        )
        if not text:
            raise runtime.provider_error_factory(
                runtime.empty_response_error(),
                requested_model,
                resolved_model_slug,
                account=account,
            )
        markdown = runtime.clean_deep_research_markdown(text)
        report_path = runtime.save_deep_research_report(config, body, latest, markdown)
        return ResearchExecutionResult(
            requested_model=requested_model,
            model_slug=resolved_model_slug,
            account=account,
            prompt=latest,
            markdown=markdown,
            report_path=report_path,
            metadata=metadata,
        )
    finally:
        runtime.finish_chatgpt_operation(operation_id)
