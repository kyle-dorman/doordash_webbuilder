"""Exercise the real SDK conversation and computer tool with a local Responses fixture."""

from collections.abc import AsyncIterator
from typing import Literal
from unittest.mock import AsyncMock, MagicMock

import httpx2
import pytest
from agents import trace
from openai import BadRequestError, omit
from openai.types.responses.computer_action import Click, ComputerAction, Keypress, Type
from playwright.async_api import Page, async_playwright
from sdk_responses import computer_call, response
from webbuilder_shopper.computer_use.browser import VIEWPORT, ShopperFailure
from webbuilder_shopper.computer_use.shopper import ModelUnavailable, SdkShopperSession
from webbuilder_shopper.computer_use.usage import MODEL, TERRA, summarize_usage

pytestmark = pytest.mark.anyio
BUTTON = Click(type="click", button="left", x=20, y=20)


@pytest.fixture
async def page() -> AsyncIterator[Page]:
    async with async_playwright() as playwright:
        async with await playwright.chromium.launch() as browser:
            yield await browser.new_page(viewport=VIEWPORT)


async def test_sdk_drives_page_and_continues_under_one_trace_and_budget(
    page: Page, responses: AsyncMock, traces: MagicMock
) -> None:
    # Finish the checkpoint on turn 2, then exhaust the shared budget on an edit action.
    responses.side_effect = [
        response(1, computer_call(BUTTON, Type(type="type", text="tea"))),
        response(2, "Ready."),
        response(3, computer_call(Type(type="type", text=" and rice"))),
    ]
    history: list[dict[str, object]] = []
    session = SdkShopperSession(page, MODEL, 3, history)
    await page.set_content(
        '<input aria-label="Items" style="position:absolute;inset:0;height:50px">'
    )
    with trace("offline shopper"):
        assert await session.run("Add tea.") == "Ready."
        assert await page.get_by_role("textbox").input_value() == "tea"
        with pytest.raises(ShopperFailure, match="3-step limit"):
            await session.run("Add rice.")
        assert await page.get_by_role("textbox").input_value() == "tea and rice"

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


async def test_sdk_prices_terra_cache_reads_and_both_write_lifetimes_per_response(
    page: Page, responses: AsyncMock, traces: MagicMock
) -> None:
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
    session = SdkShopperSession(page, TERRA, 32, history)
    with trace("offline shopper"):
        assert await session.run("Show my cart.") == "Ready."
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
async def test_sdk_rejects_actions_before_dispatch_and_stops_batch(
    page: Page, responses: AsyncMock, traces: MagicMock, action: ComputerAction, flagged: bool
) -> None:
    await page.set_content(
        "<title>untouched</title><body style='height:100vh' onclick='document.title=1' "
        "onkeydown='document.title=2'></body>"
    )
    responses.side_effect = [response(1, computer_call(action, BUTTON, flagged=flagged))]
    history: list[dict[str, object]] = []
    session = SdkShopperSession(page, MODEL, 3, history)
    with trace("offline shopper"), pytest.raises(ShopperFailure):
        await session.run("Add tea.")
    assert await page.title() == "untouched"
    assert session.steps == responses.await_count == 1
    blocked = [event for event in history if event.get("outcome") == "blocked"]
    assert len(blocked) == 1 and blocked[0]["call_id"] == "call_1"
    traces.on_trace_end.assert_called_once()


@pytest.mark.parametrize("flag_last_call", [False, True], ids=["execute-both", "block-whole-turn"])
async def test_two_computer_calls_in_one_response(
    flag_last_call: bool, page: Page, responses: AsyncMock, traces: MagicMock
) -> None:
    await page.set_content('<input style="position:absolute;inset:0;height:50px">')
    turn = response(1, computer_call(BUTTON, Type(type="type", text="tea")))
    second = computer_call(Type(type="type", text=" and rice"), flagged=flag_last_call)
    turn.output.append(second.model_copy(update={"id": "cu_2", "call_id": "call_2"}))
    responses.side_effect = [turn, response(2, "Ready.")]
    history: list[dict[str, object]] = []
    session = SdkShopperSession(page, MODEL, 2, history)
    with trace("offline shopper"):
        if flag_last_call:
            with pytest.raises(ShopperFailure, match="human review"):
                await session.run("Add both items.")
            assert await page.get_by_role("textbox").input_value() == ""
            assert not any(event["event"] == "action" for event in history)
        else:
            assert await session.run("Add both items.") == "Ready."
            assert await page.get_by_role("textbox").input_value() == "tea and rice"
            assert [
                (event["step"], event["call_id"]) for event in history if event["event"] == "action"
            ] == [(1, "call_1"), (1, "call_1"), (1, "call_2")]
            assert [
                (event["step"], event["call_id"])
                for event in history
                if event["event"] == "screenshot"
            ] == [(0, None), (1, "call_1"), (1, "call_2")]


async def test_no_edit_turn_is_released_after_final_answer_spends_last_turn(
    page: Page, responses: AsyncMock, traces: MagicMock
) -> None:
    responses.side_effect = [response(1, "Ready.")]
    session = SdkShopperSession(page, MODEL, 1, [])
    with trace("offline shopper"):
        assert await session.run("Show my cart.") == "Ready."
        with pytest.raises(ShopperFailure, match="1-step limit"):
            await session.run("Change my order.")
    assert responses.await_count == session.steps == 1
    assert [event["text"] for event in session.history if event["event"] == "request"] == [
        "Show my cart."
    ]


@pytest.mark.parametrize(
    ("status", "failure"), [("incomplete", ShopperFailure), ("failed", ModelUnavailable)]
)
async def test_sdk_terminal_response_retains_usage_and_stops_before_actions(
    page: Page,
    responses: AsyncMock,
    traces: MagicMock,
    status: Literal["incomplete", "failed"],
    failure: type[Exception],
) -> None:
    await page.set_content(
        "<title>untouched</title><body style='height:100vh' onclick='document.title=1'></body>"
    )
    terminal = response(1, computer_call(BUTTON))
    terminal.status = status
    responses.side_effect = [terminal]
    history: list[dict[str, object]] = []
    session = SdkShopperSession(page, MODEL, 3, history)
    with trace("offline shopper"), pytest.raises(failure):
        await session.run("Add tea.")
    assert await page.title() == "untouched"
    assert session.steps == responses.await_count == 1
    last = history[-1]
    assert last["event"] == "response" and last["status"] == status
    assert isinstance(last["usage"], dict) and last["usage"]["total_tokens"] == 48


async def test_api_error_reports_reason_without_echoing_images_or_keys(
    page: Page, responses: AsyncMock, traces: MagicMock, caplog: pytest.LogCaptureFixture
) -> None:
    message = "Invalid image data:image/png;base64,sensitivepixels or key sk-sensitive."
    responses.side_effect = BadRequestError(
        message,
        response=httpx2.Response(
            400,
            request=httpx2.Request("POST", "https://example.test"),
            headers={"x-request-id": "req_1"},
        ),
        body={"message": message},
    )
    session = SdkShopperSession(page, MODEL, 3, [])
    with trace("offline shopper"), pytest.raises(ModelUnavailable) as error:
        await session.run("Find hours.")
    assert "Invalid image [redacted] or key [redacted]" in str(error.value)
    assert "request req_1" in str(error.value)
    spans = [call.args[0].export() for call in traces.on_span_end.call_args_list]
    assert spans
    for text in (str(error.value), str(session.history), str(spans), caplog.text):
        assert "sensitivepixels" not in text and "sk-sensitive" not in text
