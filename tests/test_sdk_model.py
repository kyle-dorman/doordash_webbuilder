"""Exercise the real SDK conversation and computer tool with a local Responses fixture."""

from collections.abc import Iterator
from typing import Literal
from unittest.mock import AsyncMock, MagicMock

import pytest
from agents.testing import assistant_message
from agents.tracing import TracingProcessor, get_trace_provider, set_trace_provider
from agents.tracing.provider import DefaultTraceProvider
from openai import omit
from openai.resources.responses import AsyncResponses
from openai.types.responses import Response, ResponseComputerToolCall
from openai.types.responses.computer_action import Click, ComputerAction, Keypress, Type
from playwright.sync_api import Page, sync_playwright
from webbuilder_shopper.computer_model import VIEWPORT, ModelUnavailable, ShopperFailure
from webbuilder_shopper.sdk_model import SdkShopperSession
from webbuilder_shopper.shopper_usage import TERRA, summarize_usage

MODEL = "gpt-5.4-2026-03-05"
BUTTON = Click(type="click", button="left", x=20, y=20)


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
    output = assistant_message(item) if isinstance(item, str) else item
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


def test_sdk_drives_page_and_continues_under_one_trace_and_budget(
    responses: AsyncMock, traces: MagicMock
) -> None:
    # Finish the checkpoint on turn 2, then exhaust the shared budget on an edit action.
    responses.side_effect = [
        response(1, computer_call(BUTTON, Type(type="type", text="tea"))),
        response(2, "Ready."),
        response(3, computer_call(Type(type="type", text=" and rice"))),
    ]
    history: list[dict[str, object]] = []
    session = SdkShopperSession(MODEL, 3, history)
    with sync_playwright() as playwright, playwright.chromium.launch() as browser:
        page = browser.new_page(viewport=VIEWPORT)
        page.set_content('<input aria-label="Items" style="position:absolute;inset:0;height:50px">')
        with session.attempt_trace:
            assert session.run(page, "Add tea.") == "Ready."
            assert page.get_by_role("textbox").input_value() == "tea"
            with pytest.raises(ShopperFailure, match="3-step limit"):
                session.run(page, "Add rice.")
            assert page.get_by_role("textbox").input_value() == "tea and rice"

    assert session.steps == responses.await_count == 3
    traces.on_trace_start.assert_called_once()
    traces.on_trace_end.assert_called_once_with(traces.on_trace_start.call_args.args[0])
    trace_id = traces.on_trace_start.call_args.args[0].trace_id
    assert all(call.args[0].trace_id == trace_id for call in traces.on_span_start.call_args_list)
    assert traces.on_span_start.call_count > 0
    initial, feedback, edit = [call.kwargs for call in responses.await_args_list]
    for call in (initial, feedback, edit):
        assert call["model"] == MODEL and call["tools"] == [{"type": "computer"}]
        assert call["max_output_tokens"] == 2048
        assert call.get("prompt_cache_key", omit) is omit
        assert call["reasoning"].model_dump(exclude_none=True) == {"effort": "low"}
        assert "preserve_raw_usage" not in call
    initial_content = initial["input"][0]["content"]
    assert initial_content[0] == {"type": "input_text", "text": "Add tea."}
    assert initial_content[1]["image_url"].startswith("data:image/png;base64,")
    assert initial_content[1]["detail"] == "original"
    assert feedback["previous_response_id"] == "resp_1"
    assert len(feedback["input"]) == 1
    tool_result = feedback["input"][0]
    assert tool_result["type"] == "computer_call_output" and tool_result["call_id"] == "call_1"
    assert tool_result["output"]["image_url"].startswith("data:image/png;base64,")
    assert tool_result["output"]["image_url"] != initial_content[1]["image_url"]
    assert edit["previous_response_id"] == "resp_2"
    assert edit["input"] == [{"role": "user", "content": "Add rice."}]
    turns = [event for event in history if event["event"] == "response"]
    assert [turn["step"] for turn in turns] == [1, 2, 3]
    assert [turn["id"] for turn in turns] == ["resp_1", "resp_2", "resp_3"]
    assert all(
        turn["usage"]
        == {
            "input_tokens": 40,
            "cached_input_tokens": 10,
            "cache_write_input_tokens": 0,
            "output_tokens": 8,
            "reasoning_tokens": 3,
            "total_tokens": 48,
        }
        for turn in turns
    )


def test_sdk_prices_terra_cache_reads_and_both_write_lifetimes_per_response(
    responses: AsyncMock, traces: MagicMock
) -> None:
    page = MagicMock(spec=Page)
    page.screenshot.return_value = b"pixels"
    short = response(1, computer_call(BUTTON))
    long = response(2, "Ready.")
    for reply, inputs in ((short, 272_000), (long, 272_001)):
        reply.model = TERRA
        assert reply.usage is not None
        reply.usage.input_tokens = inputs
        reply.usage.total_tokens = inputs + reply.usage.output_tokens
        reply.usage.input_tokens_details = type(reply.usage.input_tokens_details).model_validate(
            {
                "cached_tokens": 10,
                "cache_write_tokens": 25,
                "cache_write_tokens_details": {"ttl_30m_tokens": 20, "ttl_12h_tokens": 5},
            }
        )
    responses.side_effect = [short, long]
    history: list[dict[str, object]] = []
    session = SdkShopperSession(TERRA, 32, history)
    with session.attempt_trace:
        assert session.run(page, "Show my cart.") == "Ready."
    first = next(event for event in history if event["event"] == "response")
    assert short.usage and first["raw_usage"] == short.usage.model_dump(exclude_unset=True)
    summary = summarize_usage(history, TERRA, turns=2)
    assert summary["ttl_30m_tokens"] == 40 and summary["ttl_12h_tokens"] == 10
    # 272,000 is short context. Only the second response gets long-context rates.
    assert summary["estimated_cost_usd"] == (272_043 + 544_068) / 1_000_000
    history.append({"event": "response", "usage": None})
    partial = summarize_usage(history, TERRA, turns=3)
    assert partial["priced_responses"] == 2 and partial["estimated_cost_usd"] is None
    assert partial["reported_cost_usd"] == summary["estimated_cost_usd"]


def test_terra_requires_cache_write_counts_to_price_a_historical_response() -> None:
    usage = {
        "input_tokens": 2500,
        "cached_input_tokens": 1000,
        "output_tokens": 20,
        "reasoning_tokens": 5,
        "total_tokens": 2520,
    }
    history: list[dict[str, object]] = [{"event": "response", "usage": usage}]
    assert summarize_usage(history, TERRA)["estimated_cost_usd"] is None
    usage["cache_write_input_tokens"] = 10
    assert summarize_usage(history, TERRA)["estimated_cost_usd"] is None


@pytest.mark.parametrize(
    ("action", "flagged"),
    [
        (BUTTON, True),
        (Click(type="click", button="left", keys=["Control"], x=20, y=20), False),
        (Click(type="click", button="left", x=1280, y=0), False),
        (Keypress(type="keypress", keys=["Control", "l"]), False),
    ],
    ids=["safety-check", "modified-click", "outside-viewport", "browser-shortcut"],
)
def test_sdk_rejects_actions_before_dispatch_and_stops_batch(
    responses: AsyncMock, traces: MagicMock, action: ComputerAction, flagged: bool
) -> None:
    responses.side_effect = [response(1, computer_call(action, BUTTON, flagged=flagged))]
    page = MagicMock(spec=Page)
    page.screenshot.return_value = b"pixels"
    history: list[dict[str, object]] = []
    session = SdkShopperSession(MODEL, 3, history)
    with session.attempt_trace, pytest.raises(ShopperFailure):
        session.run(page, "Add tea.")
    page.mouse.click.assert_not_called()
    page.keyboard.press.assert_not_called()
    assert session.steps == responses.await_count == 1
    blocked = [event for event in history if event.get("outcome") == "blocked"]
    assert len(blocked) == 1 and blocked[0]["call_id"] == "call_1"
    traces.on_trace_end.assert_called_once()


def test_no_edit_turn_is_released_after_final_answer_spends_last_turn(
    responses: AsyncMock, traces: MagicMock
) -> None:
    page = MagicMock(spec=Page)
    page.screenshot.return_value = b"pixels"
    responses.side_effect = [response(1, "Ready.")]
    session = SdkShopperSession(MODEL, 1, [])
    with session.attempt_trace:
        assert session.run(page, "Show my cart.") == "Ready."
        with pytest.raises(ShopperFailure, match="1-step limit"):
            session.run(page, "Change my order.")
    assert responses.await_count == session.steps == 1


@pytest.mark.parametrize(
    ("status", "failure"), [("incomplete", ShopperFailure), ("failed", ModelUnavailable)]
)
def test_sdk_terminal_response_retains_usage_and_stops_before_actions(
    responses: AsyncMock,
    traces: MagicMock,
    status: Literal["incomplete", "failed"],
    failure: type[Exception],
) -> None:
    page = MagicMock(spec=Page)
    page.screenshot.return_value = b"pixels"
    terminal = response(1, computer_call(BUTTON))
    terminal.status = status
    responses.side_effect = [terminal]
    history: list[dict[str, object]] = []
    session = SdkShopperSession(MODEL, 3, history)
    with session.attempt_trace, pytest.raises(failure):
        session.run(page, "Add tea.")
    page.mouse.click.assert_not_called()
    assert session.steps == responses.await_count == 1
    last = history[-1]
    assert last["event"] == "response" and last["status"] == status
    assert isinstance(last["usage"], dict) and last["usage"]["total_tokens"] == 48
