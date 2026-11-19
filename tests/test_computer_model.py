from unittest.mock import MagicMock, patch

import httpx2
import pytest
from openai import BadRequestError
from openai.types.responses import ResponseUsage
from openai.types.responses.computer_action import Click, Keypress, Scroll, Type
from openai.types.responses.response_computer_tool_call import PendingSafetyCheck
from playwright.sync_api import Page
from webbuilder_shopper.computer_model import ModelUnavailable, ShopperFailure, ShopperSession
from webbuilder_shopper.shopper_usage import MODEL, summarize_usage


def test_native_turns_only_send_screenshots_and_share_one_edit_budget() -> None:
    # Keep real SDK action shapes and drive both halves of the same conversation.
    page = MagicMock(spec=Page)
    page.screenshot.return_value = b"pixels"
    tool = MagicMock(type="computer_call", call_id="c1", pending_safety_checks=[])
    tool.actions = [
        Click(type="click", button="left", x=12, y=15),
        Type(type="type", text="hello"),
        Scroll(type="scroll", x=50, y=75, scroll_x=0, scroll_y=20),
    ]
    answer = MagicMock(type="message", phase="final_answer")
    answer.content = [MagicMock(type="output_text", text="Ready.")]
    with patch("webbuilder_shopper.computer_model.OpenAI") as client:
        create = client.return_value.__enter__.return_value.responses.create
        usage = ResponseUsage.model_validate(
            {
                "input_tokens": 100,
                "output_tokens": 30,
                "total_tokens": 130,
                "input_tokens_details": {"cached_tokens": 80, "cache_write_tokens": 0},
                "output_tokens_details": {"reasoning_tokens": 20},
            }
        )
        create.side_effect = [
            MagicMock(id="r1", _request_id="q1", status="completed", output=[tool], usage=usage),
            MagicMock(id="r2", status="completed", output=[answer], usage=usage),
            MagicMock(id="r3", status="completed", output=[tool], usage=usage),
            MagicMock(id="r4", status="completed", output=[answer]),
        ]
        history: list[dict[str, object]] = []
        session = ShopperSession("snapshot", 3, history)
        first = "Show me my cart."
        second = "Change my order."
        assert session.run(page, first) == "Ready."
        with pytest.raises(ShopperFailure, match="3-step limit"):
            session.run(page, second)
        assert session.steps == 3
        assert ShopperSession("snapshot", 3, []).run(page, first) == "Ready."

        first_call, feedback, edit, retry = [call.kwargs for call in create.call_args_list]
        assert first_call["previous_response_id"] is retry["previous_response_id"] is None
        assert feedback["previous_response_id"] == "r1" and edit["previous_response_id"] == "r2"
        screenshot = "data:image/png;base64,cGl4ZWxz"
        # The API rejects a new user image on any turn carrying previous_response_id.
        assert edit["input"] == [{"role": "user", "content": second}]
        for call, request in ((first_call, first), (retry, first)):
            assert call["tools"] == [{"type": "computer"}]
            assert call["input"] == [
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": request},
                        {"type": "input_image", "detail": "original", "image_url": screenshot},
                    ],
                }
            ]
        assert feedback["input"] == [
            {
                "type": "computer_call_output",
                "call_id": "c1",
                "output": {"type": "computer_screenshot", "image_url": screenshot},
            }
        ]
        page.mouse.click.assert_called_with(12, 15)
        page.keyboard.insert_text.assert_called_with("hello")
        page.mouse.wheel.assert_called_with(0, 20)
        actions = [event for event in history if event["event"] == "action"]
        assert len(actions) == 6
        assert all(e["outcome"] == "executed" and e["call_id"] == "c1" for e in actions)
        assert history[1]["request_id"] == "q1"
        assert summarize_usage(history, MODEL, session.steps) == {
            "input_tokens": 300,
            "cached_input_tokens": 240,
            "cache_write_input_tokens": 0,
            "ttl_30m_tokens": 0,
            "ttl_12h_tokens": 0,
            "output_tokens": 90,
            "reasoning_tokens": 60,
            "total_tokens": 390,
            "responses_with_usage": 3,
            "priced_responses": 3,
            "reported_cost_usd": 0.00156,
            "estimated_cost_usd": 0.00156,
        }
        assert summarize_usage(history, "unknown-model")["estimated_cost_usd"] is None
        assert summarize_usage(history, MODEL, session.steps + 1)["estimated_cost_usd"] is None
        history.append({"event": "response", "usage": None})
        assert summarize_usage(history, MODEL)["estimated_cost_usd"] is None


def test_browser_shortcut_is_recorded_without_being_executed() -> None:
    page = MagicMock(spec=Page)
    page.screenshot.return_value = b"pixels"
    tool = MagicMock(type="computer_call", pending_safety_checks=[])
    tool.actions = [Keypress(type="keypress", keys=["Control", "l"])]
    with patch("webbuilder_shopper.computer_model.OpenAI") as client:
        create = client.return_value.__enter__.return_value.responses.create
        create.return_value = MagicMock(id="r1", status="completed", output=[tool])
        history: list[dict[str, object]] = []
        with pytest.raises(ShopperFailure, match="Unavailable shopper action"):
            ShopperSession("snapshot", 3, history).run(page, "Find hours.")
        page.keyboard.press.assert_not_called()
        assert history[-1]["action"] == {"type": "keypress", "keys": ["Control", "l"]}
        assert history[-1]["outcome"] == "blocked"


def test_flagged_computer_call_stops_before_the_first_action() -> None:
    page = MagicMock(spec=Page)
    page.screenshot.return_value = b"pixels"
    tool = MagicMock(type="computer_call", call_id="flagged")
    tool.pending_safety_checks = [PendingSafetyCheck(id="check-1", code="test-check")]
    tool.actions = [Click(type="click", button="left", x=10, y=20)]
    with patch("webbuilder_shopper.computer_model.OpenAI") as client:
        create = client.return_value.__enter__.return_value.responses.create
        create.return_value = MagicMock(id="r1", status="completed", output=[tool], usage=None)
        history: list[dict[str, object]] = []
        with pytest.raises(ShopperFailure, match="requires human review"):
            ShopperSession("snapshot", 3, history).run(page, "Show me my cart.")
    page.mouse.click.assert_not_called()
    assert history[-1] == {
        "event": "computer_call",
        "step": 1,
        "call_id": "flagged",
        "outcome": "blocked",
        "pending_safety_checks": [{"id": "check-1", "code": "test-check"}],
    }
    assert summarize_usage(history, MODEL)["estimated_cost_usd"] is None


def test_api_error_reports_reason_without_echoing_images_or_keys() -> None:
    page = MagicMock(spec=Page)
    page.screenshot.return_value = b"pixels"
    body = {"message": "Invalid image data:image/png;base64,example or key sk-example."}
    error = BadRequestError(
        "bad request",
        response=httpx2.Response(400, request=httpx2.Request("POST", "https://example.test")),
        body=body,
    )
    with patch("webbuilder_shopper.computer_model.OpenAI") as client:
        client.return_value.__enter__.return_value.responses.create.side_effect = error
        with pytest.raises(ModelUnavailable) as result:
            ShopperSession("snapshot", 3, []).run(page, "Find hours.")
        assert "Invalid image [redacted] or key [redacted]" in str(result.value)
        assert "example" not in str(result.value)
