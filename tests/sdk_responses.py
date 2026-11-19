"""Local Responses API replies and an in-process SDK trace sink for offline shopper tests."""

from collections.abc import Iterator
from unittest.mock import AsyncMock, MagicMock

import pytest
from agents.testing import assistant_message
from agents.tracing import TracingProcessor, get_trace_provider, set_trace_provider
from agents.tracing.provider import DefaultTraceProvider
from openai.resources.responses import AsyncResponses
from openai.types.responses import Response, ResponseComputerToolCall
from openai.types.responses.computer_action import ComputerAction
from webbuilder_shopper.computer_use.usage import MODEL


@pytest.fixture
def traces() -> Iterator[MagicMock]:
    # Exercise the real trace scope while keeping all test spans in process.
    previous = get_trace_provider()
    provider = DefaultTraceProvider()
    processor = MagicMock(spec=TracingProcessor)
    provider.register_processor(processor)
    set_trace_provider(provider)
    try:
        yield processor
    finally:
        set_trace_provider(previous)


@pytest.fixture
def responses(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    create = AsyncMock()
    monkeypatch.setenv("OPENAI_API_KEY", "offline-test")
    monkeypatch.setattr(AsyncResponses, "create", create)
    return create


def computer_call(*actions: ComputerAction, flagged: bool = False) -> ResponseComputerToolCall:
    return ResponseComputerToolCall.model_validate(
        {
            "type": "computer_call",
            "id": "cu_1",
            "call_id": "call_1",
            "status": "completed",
            "actions": [action.model_dump(exclude_none=True) for action in actions],
            "pending_safety_checks": [{"id": "check_1", "code": "test"}] if flagged else [],
        }
    )


def response(turn: int, item: ResponseComputerToolCall | str) -> Response:
    if isinstance(item, str):
        output = assistant_message(item)
    else:
        output = item.model_copy(update={"id": f"cu_{turn}", "call_id": f"call_{turn}"})
    return Response.model_validate(
        {
            "id": f"resp_{turn}",
            "model": MODEL,
            "object": "response",
            "created_at": 1,
            "status": "completed",
            "output": [output],
            "tools": [{"type": "computer"}],
            "tool_choice": "auto",
            "parallel_tool_calls": True,
            "usage": {
                "input_tokens": 40,
                "input_tokens_details": {"cached_tokens": 10, "cache_write_tokens": 0},
                "output_tokens": 8,
                "output_tokens_details": {"reasoning_tokens": 3},
                "total_tokens": 48,
            },
        }
    )
