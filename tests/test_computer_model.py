from unittest.mock import MagicMock, patch

import httpx2
import pytest
from openai import BadRequestError
from openai.types.responses.computer_action import Click, Keypress, Scroll, Type
from playwright.sync_api import Page
from webbuilder_shopper.computer_model import ModelUnavailable, ShopperFailure, ShopperSession


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
        create.side_effect = [
            MagicMock(id="r1", status="completed", output=[tool]),
            MagicMock(id="r2", status="completed", output=[answer]),
            MagicMock(id="r3", status="completed", output=[tool]),
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
        assert len([event for event in history if event["event"] == "action"]) == 6


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
