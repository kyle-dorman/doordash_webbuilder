"""Drive the actual SDK and Chromium against a generated store, with offline model replies."""

import base64
import hashlib
import json
from collections.abc import AsyncIterator
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal
from unittest.mock import AsyncMock
from urllib.parse import urlsplit

import pytest
from openai import omit
from openai.types.responses import Response, ResponseComputerToolCall
from openai.types.responses.computer_action import Click
from playwright.async_api import Browser, BrowserContext, Page, async_playwright
from sdk_responses import computer_call, response
from webbuilder_static.storefront import generate
from webbuilder_mock_backend.server import Catalog, OrderHandler, load_catalog
from webbuilder_shopper.computer_use.report import new_report
from webbuilder_shopper.computer_use.runner import CHANGE_REQUEST, REQUESTS, run_suite
from webbuilder_shopper.computer_use.usage import MODEL
from webbuilder_shopper.grading import RICE, ROLLS, STORE_ID, TEA

pytestmark = [pytest.mark.anyio, pytest.mark.usefixtures("traces")]


@pytest.fixture
async def browser() -> AsyncIterator[Browser]:
    async with async_playwright() as playwright, await playwright.chromium.launch() as chromium:
        yield chromium


@pytest.fixture
def site(tmp_path: Path) -> tuple[Path, Catalog]:
    # A tiny feed published by the real generator. No external feed or photos are needed.
    items = [
        {
            "id": item_id,
            "name": name,
            "price": {
                "unit_amount": cents,
                "currency": "USD",
                "display_string": f"${cents / 100:.2f}",
            },
        }
        for item_id, name, cents in (
            ("140247117", RICE, 250),
            ("140240246", ROLLS, 850),
            ("548484849", TEA, 450),
        )
    ]
    location = {
        "store_id": STORE_ID,
        "address": {
            "street": "219 Southwest 9th Avenue",
            "city": "Portland",
            "state": "OR",
            "zip_code": "97205",
            "country": "US",
        },
        "phone": "+15037197273",
        "timezone": "US/Pacific",
        "open_hours": [],
    }
    store = {
        "store_id": STORE_ID,
        "store_header": {"data": {"name": "Thai Peacock", "cuisine_type": "Thai"}},
        "business_profile": {"locations": [location]},
        "menu_book": {"item_lists": [{"name": "Menu", "items": items}]},
    }
    feed = tmp_path / "feed.json"
    feed.write_text(json.dumps({"restaurants": [store]}), encoding="utf-8")
    return generate(feed, STORE_ID, tmp_path / "site").parent, load_catalog(feed)


CONTACT = "219 Southwest 9th Avenue, Portland, OR 97205 · (503) 719-7273"
HOURS = "Tuesday 11:30 AM–9:15 PM. Friday 11:00 AM–9:45 PM."


def click(x: int, y: int) -> Click:
    return Click(type="click", button="left", x=x, y=y)


# Recorded button centers for the generated three-item fixture at 1280 × 900.
MENU = computer_call(click(1001, 34))
CART = click(1195, 34)
ADD_RICE, ADD_ROLLS, ADD_TEA = click(382, 348), click(837, 348), click(382, 453)
TEA_AND_RICE = computer_call(ADD_TEA, ADD_RICE, CART)
PLACE_BOTH = computer_call(click(1029, 564))
EDIT_AND_PLACE = computer_call(click(939, 319), click(1066, 433), click(1029, 465))
CART_REPLY = "Here is your cart with one tea and one rice."
ORDER_REPLY = "Your order was placed."


async def test_stories_retry_independently_and_grade_cart_before_follow_up(
    browser: Browser, site: tuple[Path, Catalog], responses: AsyncMock, tmp_path: Path
) -> None:
    directory, catalog = site
    evidence = tmp_path / "evidence"
    index = directory / "index.html"
    index_hash = hashlib.sha256(index.read_bytes()).hexdigest()
    # The first hours attempt checks out before answering. Its retry must get a fresh mock.
    # For change, try an incomplete cart, then a correct cart after a premature checkout.
    place_rolls_and_rice = computer_call(ADD_ROLLS, ADD_ROLLS, ADD_RICE, CART)
    incomplete_cart = computer_call(ADD_TEA, CART)
    attempt_replies: list[list[str | ResponseComputerToolCall]] = [
        [CONTACT],
        [MENU, TEA_AND_RICE, PLACE_BOTH, HOURS],  # Checked out during lookup
        [HOURS],
        ["32 oz, $14.50"],
        ["32 oz, $14.50"],
        ["32 oz, $14.50"],
        [MENU, place_rolls_and_rice, PLACE_BOTH, ORDER_REPLY],
        [MENU, incomplete_cart, CART_REPLY],  # Grader sees only tea
        [MENU, TEA_AND_RICE, PLACE_BOTH, MENU, TEA_AND_RICE, CART_REPLY],  # Early order
        [MENU, TEA_AND_RICE, CART_REPLY, EDIT_AND_PLACE, ORDER_REPLY],
    ]
    replies = [item for attempt in attempt_replies for item in attempt]
    previous_cart_frame: bytes | None = None
    contexts: set[BrowserContext] = set()
    opening_page: Page | None = None

    def next_reply(**options: Any) -> Response:
        nonlocal previous_cart_frame, opening_page
        turn = responses.await_count
        if turn == 1:
            # Later attempts must continue to serve the snapshot captured before this edit.
            index.write_text("<html><title>source build was replaced</title></html>")
        inputs = options["input"]
        if isinstance(inputs[0].get("content"), list):
            (context,) = browser.contexts
            assert context not in contexts
            contexts.add(context)
            (opening_page,) = context.pages
            assert urlsplit(opening_page.url).path == "/"
        if turn == len(replies) - 1:
            assert browser.contexts[0].pages == [opening_page]
            assert inputs == [{"role": "user", "content": CHANGE_REQUEST}]
            assert options["previous_response_id"] == f"resp_{turn - 1}"
            assert (evidence / "change-3-cart.png").read_bytes() == previous_cart_frame
        if inputs[0].get("type") == "computer_call_output":
            image_url = inputs[0]["output"]["image_url"]
            previous_cart_frame = base64.b64decode(image_url.split(",", 1)[1], validate=True)
        return response(turn, replies[turn - 1])

    responses.side_effect = next_reply
    report = new_report(directory, MODEL, 32)
    await run_suite(browser, catalog, evidence, report)
    assert report["status"] == "failed"
    assert report["runner"] == "sdk" and report["model"] == MODEL
    assert "openai-agents" in report["versions"] and report["step_limit"] == 32
    assert (
        report["build_sha256"]
        and json.loads((evidence / "build-files.json").read_text())["index.html"] == index_hash
    )
    assert report["first_attempt_passes"] == 2 and report["within_three_passes"] == 4
    attempts = report["attempts"]
    assert [(a["story"], a["attempt"], a["status"]) for a in attempts] == [
        ("contact", 1, "passed"),
        ("hours", 1, "failed"),
        ("hours", 2, "passed"),
        ("soup", 1, "failed"),
        ("soup", 2, "failed"),
        ("soup", 3, "failed"),
        ("place", 1, "passed"),
        ("change", 1, "failed"),
        ("change", 2, "failed"),
        ("change", 3, "passed"),
    ]
    first_hours, retry_hours = (a for a in attempts if a["story"] == "hours")
    assert len(first_hours["submissions"]) == 1 and "zero" in first_hours["reason"].lower()
    assert retry_hours["submissions"] == () and first_hours["answers"] == retry_hours["answers"]
    (placed,) = (a for a in attempts if a["story"] == "place")
    assert len(placed["submissions"]) == 1

    missing_rice, ordered_early, passed = (a for a in attempts if a["story"] == "change")
    assert missing_rice["initial_cart"] == [(TEA, 1)] and missing_rice["submissions"] == ()
    assert missing_rice["checkpoint_submission_count"] == 0
    assert ordered_early["initial_cart"] == [(TEA, 1), (RICE, 1)]
    assert ordered_early["checkpoint_submission_count"] == 1
    assert len(ordered_early["submissions"]) == 1 and "before" in ordered_early["reason"]
    for failed in (missing_rice, ordered_early):
        assert failed["answers"] == [CART_REPLY] and failed["checkpoint_screenshot"] is None
    assert passed["checkpoint_submission_count"] == 0
    assert passed["initial_cart"] == [(TEA, 1), (RICE, 1)]
    assert passed["answers"] == [CART_REPLY, ORDER_REPLY] and passed["steps"] == 5
    assert passed["confirmation"] == {
        "items": [{"name": TEA, "quantity": 2, "unit_price": "$4.50", "line_total": "$9.00"}],
        "total": "$9.00",
    }
    assert passed["submissions"] == (
        {
            "store_id": STORE_ID,
            "items": [
                {
                    "item_id": "548484849",
                    "name": TEA,
                    "quantity": 2,
                    "unit_price_cents": 450,
                    "line_total_cents": 900,
                }
            ],
            "subtotal_cents": 900,
        },
    )
    assert passed["screenshot"] and passed["checkpoint_screenshot"]
    assert (evidence / passed["screenshot"]).read_bytes() != (
        evidence / passed["checkpoint_screenshot"]
    ).read_bytes()

    calls = responses.await_args_list
    assert len(calls) == sum(a["steps"] for a in attempts) == len(replies)
    # Per reply: 30 ordinary and 10 cached input tokens, 8 output tokens, at GPT-5.4 rates.
    assert report["reported_total_tokens"] == len(replies) * 48
    all_cost = len(replies) * Decimal("0.0001975")
    assert report["estimated_total_cost_usd"] == float(all_cost)
    assert report["estimated_cost_per_passing_story_usd"] == float(all_cost / 4)
    assert len({a["trace_id"] for a in attempts}) == len(attempts)
    offset = 0
    for attempt in attempts:
        assert attempt["trace_id"]
        first = calls[offset].kwargs
        offset += attempt["steps"]
        assert first.get("previous_response_id", omit) is omit
        assert first["input"][0]["content"][0]["text"] == REQUESTS[attempt["story"]]
        history = json.loads((evidence / attempt["action_history"]).read_text())
        frames = [event["screenshot"] for event in history if event["event"] == "screenshot"]
        assert frames
        for frame in frames:
            assert (evidence / frame).read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
        assert (evidence / frames[0]).read_bytes() == base64.b64decode(
            first["input"][0]["content"][1]["image_url"].split(",", 1)[1], validate=True
        )
        expected = [REQUESTS[attempt["story"]]]
        if attempt is passed:
            expected.append(CHANGE_REQUEST)
        assert [h["text"] for h in history if h["event"] == "request"] == expected
        if attempt["steps"] > 1:
            assert any(h["event"] == "action" for h in history)
        assert attempt["screenshot"] and (evidence / attempt["screenshot"]).is_file()
        assert attempt["usage"]["total_tokens"] == attempt["steps"] * 48
    assert json.loads((evidence / "report.json").read_text()) == json.loads(json.dumps(report))


async def test_edit_keeps_checkpoint_when_follow_up_exhausts_remaining_turn(
    responses: AsyncMock, browser: Browser, site: tuple[Path, Catalog], tmp_path: Path
) -> None:
    directory, catalog = site
    evidence = tmp_path / "evidence"
    # The cart reply uses turn 3. After the edit action on turn 4 the model cannot reply.
    replies: list[str | ResponseComputerToolCall] = [
        MENU,
        TEA_AND_RICE,
        CART_REPLY,
        EDIT_AND_PLACE,
    ] * 3
    responses.side_effect = [response(i, item) for i, item in enumerate(replies, 1)]
    report = new_report(directory, MODEL, 4, story="change")
    await run_suite(browser, catalog, evidence, report)
    assert report["status"] == "failed" and len(report["attempts"]) == 3
    assert responses.await_count == 12
    for attempt in report["attempts"]:
        assert attempt["steps"] == 4 and "4-step limit" in attempt["reason"]
        assert attempt["answers"] == [CART_REPLY]
        assert attempt["checkpoint_screenshot"] and attempt["screenshot"]
        assert (evidence / attempt["checkpoint_screenshot"]).read_bytes() != (
            evidence / attempt["screenshot"]
        ).read_bytes()


@pytest.mark.parametrize("outage", ["model", "browser", "mock"])
async def test_service_loss_stops_suite_and_preserves_finished_attempt(
    outage: Literal["model", "browser", "mock"],
    monkeypatch: pytest.MonkeyPatch,
    browser: Browser,
    responses: AsyncMock,
    site: tuple[Path, Catalog],
    tmp_path: Path,
) -> None:
    directory, catalog = site
    if outage == "mock":

        def unavailable(handler: OrderHandler) -> None:
            handler.reply(503, {"error": "Mock unavailable"})

        monkeypatch.setattr(OrderHandler, "do_POST", unavailable)

    async def next_reply(**options: Any) -> Response:
        turn = responses.await_count
        if turn == 1:
            return response(turn, CONTACT)
        if outage == "browser":
            await browser.close()
            return response(turn, HOURS)
        if outage == "model":
            terminal = response(turn, HOURS)
            terminal.status = "failed"
            terminal.usage = None
            return terminal
        # Prompt the shopper to cause a real POST while the mock service is unavailable.
        return response(turn, [MENU, TEA_AND_RICE, PLACE_BOTH][turn - 2])

    responses.side_effect = next_reply
    evidence = tmp_path / "evidence"
    report = new_report(directory, MODEL, 32)
    await run_suite(browser, catalog, evidence, report)
    assert report["status"] == "incomplete" and report["reason"]
    assert report["first_attempt_passes"] == report["within_three_passes"] == 1
    assert [(a["story"], a["attempt"], a["status"]) for a in report["attempts"]] == [
        ("contact", 1, "passed"),
        ("hours", 1, "incomplete"),
    ]
    assert report["attempts"][0]["answers"] == [CONTACT]
    if outage == "model":
        assert report["reported_total_tokens"] == 48
        assert report["estimated_total_cost_usd"] is None
        assert report["estimated_cost_per_passing_story_usd"] is None
    interrupted = report["attempts"][1]
    assert interrupted["trace_id"] and (evidence / interrupted["action_history"]).is_file()
    assert interrupted["screenshot"] and (evidence / interrupted["screenshot"]).is_file()
    assert json.loads((evidence / "report.json").read_text()) == json.loads(json.dumps(report))
