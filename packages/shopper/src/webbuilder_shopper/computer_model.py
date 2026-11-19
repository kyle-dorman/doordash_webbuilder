"""Drive a single shopper conversation through the Responses computer tool."""

import base64
import re
from collections.abc import Callable
from typing import Final, Literal

from openai import APIStatusError, OpenAI, OpenAIError
from openai.types.responses import ResponseInputParam
from openai.types.responses.computer_action import ComputerAction
from openai.types.responses.response_computer_tool_call import ResponseComputerToolCall
from playwright.sync_api import Error, Page, ViewportSize

from .shopper_usage import token_counts

VIEWPORT: ViewportSize = {"width": 1280, "height": 900}
REASONING: Final[Literal["low"]] = "low"
MAX_OUTPUT_TOKENS = 2048
MODEL_SETTINGS = {
    "tool": "computer",
    "reasoning_effort": REASONING,
    "max_output_tokens": MAX_OUTPUT_TOKENS,
    "viewport": VIEWPORT,
    "screenshot_format": "png",
    "step_unit": "one model response, including the final answer and any batched actions",
}

INSTRUCTIONS = (
    "You are a shopper using the pictured restaurant website. Fulfill the user's current "
    "request using only the visible page and the computer tool. Click page controls, scroll "
    "and type in page fields. Browser shortcuts and browser chrome are unavailable. "
    "For a lookup, give a concise final answer with all requested facts; label each requested "
    "day when giving hours. When asked to show something, leave it visible and reply. "
    "For an order, use the site's simulated checkout and leave its confirmation visible."
)

# In-page keyboard operations. Chords and browser shortcuts do not reach Chromium.
_PAGE_KEYS = {
    key.lower(): key
    for key in (
        "Tab",
        "Enter",
        "Escape",
        "Backspace",
        "Delete",
        "Home",
        "End",
        "PageUp",
        "PageDown",
        "ArrowUp",
        "ArrowDown",
        "ArrowLeft",
        "ArrowRight",
        "Space",
    )
}


class ShopperFailure(ValueError):
    """The shopper finished unsuccessfully or exhausted an attempt's budget."""


class ModelUnavailable(RuntimeError):
    """The model service could not complete a response."""


def _status_detail(error: APIStatusError) -> str:
    message = error.body.get("message") if isinstance(error.body, dict) else None
    if not isinstance(message, str):
        return str(error.code or error.__class__.__name__)
    message = re.sub(
        r"(?i)data:image/\S+|\bsk-[\w*-]+|[A-Za-z0-9+/=_-]{64,}", "[redacted]", message
    )
    return " ".join(message.split())[:300]


def _act(page: Page, action: ComputerAction) -> None:
    if getattr(action, "keys", None) and action.type != "keypress":
        raise ShopperFailure("Modified pointer actions are unavailable")
    if action.type in ("click", "double_click", "move", "scroll"):
        if not (0 <= action.x < VIEWPORT["width"] and 0 <= action.y < VIEWPORT["height"]):
            raise ShopperFailure(
                f"Shopper targeted a point outside the viewport: {action.x, action.y}"
            )
    if action.type == "click" and action.button == "left":
        page.mouse.click(action.x, action.y)
    elif action.type == "double_click":
        page.mouse.dblclick(action.x, action.y)
    elif action.type == "move":
        page.mouse.move(action.x, action.y)
    elif action.type == "scroll":
        page.mouse.move(action.x, action.y)
        page.mouse.wheel(action.scroll_x, action.scroll_y)
    elif action.type == "type":
        page.keyboard.insert_text(action.text)
    elif (
        action.type == "keypress" and len(action.keys) == 1 and action.keys[0].lower() in _PAGE_KEYS
    ):
        page.keyboard.press(_PAGE_KEYS[action.keys[0].lower()])
    elif action.type == "wait":
        page.wait_for_timeout(500)
    elif action.type != "screenshot":
        raise ShopperFailure(f"Unavailable shopper action: {action.model_dump(exclude_none=True)}")


def check_safety(
    call: ResponseComputerToolCall, history: list[dict[str, object]], step: int
) -> None:
    if call.pending_safety_checks:
        history.append(
            {
                "event": "computer_call",
                "step": step,
                "call_id": call.call_id,
                "outcome": "blocked",
                "pending_safety_checks": [
                    check.model_dump(exclude_none=True) for check in call.pending_safety_checks
                ],
            }
        )
        raise ShopperFailure("Shopper action requires human review")


def execute_action(
    page: Page, action: ComputerAction, history: list[dict[str, object]], step: int, call_id: str
) -> None:
    event: dict[str, object] = {
        "event": "action",
        "step": step,
        "call_id": call_id,
        "action": action.model_dump(exclude_none=True),
    }
    history.append(event)
    try:
        _act(page, action)
    except (ShopperFailure, Error) as error:
        event["outcome"] = "blocked" if isinstance(error, ShopperFailure) else "error"
        event["reason"] = str(error)
        raise
    event["outcome"] = "executed"


class ShopperSession:
    """One conversation and turn budget, including both requests of a multi-stage story."""

    def __init__(self, model: str, step_limit: int, history: list[dict[str, object]]) -> None:
        self.model = model
        self.step_limit = step_limit
        self.history = history
        self.steps = 0
        self.on_step: Callable[[], None] | None = None
        self.last_screenshot: bytes | None = None
        self._response_id: str | None = None

    def _image(self, page: Page) -> str:
        self.last_screenshot = page.screenshot(type="png", scale="css")
        return "data:image/png;base64," + base64.b64encode(self.last_screenshot).decode("ascii")

    def run(self, page: Page, request: str) -> str:
        self.history.append({"event": "request", "text": request})
        inputs: ResponseInputParam = [{"role": "user", "content": request}]
        if self._response_id is None:
            # The computer tool accepts a user image only at the start of its conversation.
            # Subsequent user requests retain the last view via previous_response_id.
            inputs = [
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": request},
                        {
                            "type": "input_image",
                            "detail": "original",
                            "image_url": self._image(page),
                        },
                    ],
                }
            ]
        try:
            with OpenAI(max_retries=0, timeout=90) as client:
                return self._respond(client, page, inputs)
        except APIStatusError as error:
            raise ModelUnavailable(
                f"OpenAI returned HTTP {error.status_code} ({_status_detail(error)}), "
                f"request {error.request_id}"
            ) from error
        except OpenAIError as error:
            raise ModelUnavailable(
                f"OpenAI {type(error).__name__}; check OPENAI_API_KEY and service connectivity"
            ) from error

    def _respond(self, client: OpenAI, page: Page, inputs: ResponseInputParam) -> str:
        while self.steps < self.step_limit:
            if self.on_step:
                self.on_step()
            self.steps += 1
            response = client.responses.create(
                model=self.model,
                instructions=INSTRUCTIONS,
                tools=[{"type": "computer"}],
                reasoning={"effort": REASONING},
                max_output_tokens=MAX_OUTPUT_TOKENS,
                previous_response_id=self._response_id,
                store=True,
                input=inputs,
            )
            self._response_id = response.id
            self.history.append(
                {
                    "event": "response",
                    "step": self.steps,
                    "id": response.id,
                    "request_id": response._request_id,
                    "usage": token_counts(response.usage),
                    "model": response.model,
                    "status": response.status,
                }
            )
            if response.status == "incomplete":
                reason = response.incomplete_details.reason if response.incomplete_details else None
                raise ShopperFailure(f"Shopper response was incomplete ({reason})")
            if response.status != "completed":
                code = response.error.code if response.error else response.status
                raise ModelUnavailable(f"OpenAI could not complete response {response.id} ({code})")

            inputs = []
            for call in response.output:
                if call.type != "computer_call":
                    continue
                check_safety(call, self.history, self.steps)
                if not call.actions:
                    raise ShopperFailure("Computer call contained no native computer actions")
                for action in call.actions:
                    if self.on_step:
                        self.on_step()
                    execute_action(page, action, self.history, self.steps, call.call_id)
                # A wheel event can still be scrolling when Playwright returns.
                page.wait_for_timeout(250)
                inputs.append(
                    {
                        "type": "computer_call_output",
                        "call_id": call.call_id,
                        "output": {"type": "computer_screenshot", "image_url": self._image(page)},
                    }
                )

            if not inputs:
                answer = "\n".join(
                    content.text
                    for message in response.output
                    if message.type == "message" and message.phase != "commentary"
                    for content in message.content
                    if content.type == "output_text"
                ).strip()
                self.history.append({"event": "answer", "step": self.steps, "text": answer})
                if not answer:
                    raise ShopperFailure("Shopper stopped without a final answer")
                return answer
        raise ShopperFailure(f"Shopper reached the {self.step_limit}-step limit")
