from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from chatgpt_api.api.config import OpenAICompatConfig
from chatgpt_api.api.research_execution import (
    ResearchExecutionResult,
    ResearchExecutionRuntime,
    execute_deep_research,
)


def _runtime(tmp_path: Path, *, text: str = "## Finding\n\nUseful work.") -> ResearchExecutionRuntime:
    async def collect(*args, **kwargs):
        return "research-acct", object(), text, {"conversation_id": "conv_1"}

    def save_report(config, body, prompt, markdown):
        path = tmp_path / "deep-research.md"
        path.write_text(markdown, encoding="utf-8")
        return path

    return ResearchExecutionRuntime(
        str_or_none=lambda value: value if isinstance(value, str) else None,
        request_is_deep_research=lambda body, requested_model: requested_model == "chatgpt-deep-research",
        resolve_model_alias=lambda model, effort: ("gpt-5-thinking", effort),
        latest_user_message_text=lambda messages: str(messages[-1]["content"]),
        latest_message_role=lambda messages: messages[-1].get("role"),
        collect_deep_research_with_accounts=collect,
        clean_deep_research_markdown=lambda value: value.strip(),
        save_deep_research_report=save_report,
        empty_response_error=lambda: RuntimeError("empty"),
        provider_error_factory=lambda *args, **kwargs: RuntimeError("provider empty"),
        finish_chatgpt_operation=lambda operation_id: None,
    )


def test_execute_deep_research_uses_shared_provider_boundary_and_saves_markdown(tmp_path: Path):
    result = asyncio.run(
        execute_deep_research(
            OpenAICompatConfig(account="test"),
            {
                "type": "deep_research",
                "model": "chatgpt-deep-research",
                "messages": [{"role": "user", "content": "research local bridges"}],
            },
            router=None,
            runtime=_runtime(tmp_path, text="  # Report\n\nDone.  "),
            operation_id="chatgptop_agent_job_123",
        )
    )

    assert isinstance(result, ResearchExecutionResult)
    assert result.account == "research-acct"
    assert result.prompt == "research local bridges"
    assert result.markdown == "# Report\n\nDone."
    assert result.report_path.read_text(encoding="utf-8") == "# Report\n\nDone."
    assert result.metadata == {"conversation_id": "conv_1"}


def test_execute_deep_research_returns_none_for_non_research_request(tmp_path: Path):
    result = asyncio.run(
        execute_deep_research(
            OpenAICompatConfig(account="test"),
            {"type": "chat", "model": "auto", "messages": [{"role": "user", "content": "hi"}]},
            router=None,
            runtime=_runtime(tmp_path),
            operation_id=None,
        )
    )

    assert result is None


def test_execute_deep_research_rejects_followup_transcripts(tmp_path: Path):
    with pytest.raises(ValueError, match="follow-up messages"):
        asyncio.run(
            execute_deep_research(
                OpenAICompatConfig(account="test"),
                {
                    "type": "deep_research",
                    "model": "chatgpt-deep-research",
                    "messages": [
                        {"role": "user", "content": "research"},
                        {"role": "assistant", "content": "old answer"},
                    ],
                },
                router=None,
                runtime=_runtime(tmp_path),
                operation_id=None,
            )
        )
