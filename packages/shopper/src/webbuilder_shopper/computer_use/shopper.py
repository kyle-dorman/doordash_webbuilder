"""Run the Agents SDK computer shopper against the harness's restricted Playwright page."""

import re
from collections import deque
from collections.abc import Callable
from typing import Final, Literal

from agents import (
    Agent,
    AgentsException,
    ComputerTool,
    MaxTurnsExceeded,
    ModelBehaviorError,
    ModelRefusalError,
    ModelResponse,
    ModelSettings,
    OpenAIResponsesModel,
    RunConfig,
    RunContextWrapper,
    RunHooks,
    Runner,
    Tool,
    TResponseInputItem,
)
from openai import APIStatusError, AsyncOpenAI, OpenAIError, omit
from openai.types.shared import Reasoning
from playwright.async_api import Page

from .browser import VIEWPORT, PlaywrightComputer, ShopperFailure
from .usage import token_counts

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


class ModelUnavailable(RuntimeError):
    """The model service could not complete a response."""


def _redact_detail(detail: str) -> str:
    clean = re.sub(r"(?i)data:image/\S+|\bsk-[\w*-]+|[A-Za-z0-9+/=_-]{64,}", "[redacted]", detail)
    return " ".join(clean.split())[:300]


def _status_detail(error: APIStatusError) -> str:
    message = error.body.get("message") if isinstance(error.body, dict) else None
    if not isinstance(message, str):
        message = str(error.code or error.__class__.__name__)
    return _redact_detail(message)


class SdkShopperSession(RunHooks[None]):
    """Run customer requests on one page, sharing the SDK conversation and turn budget."""

    def __init__(
        self,
        page: Page,
        model: str,
        step_limit: int,
        history: list[dict[str, object]],
        *,
        on_step: Callable[[], None] | None = None,
        save_observation: Callable[[bytes], str] | None = None,
    ) -> None:
        self.model = model
        self.step_limit = step_limit
        self.history = history
        self.steps = 0
        self.on_step = on_step
        self.computer = PlaywrightComputer(page, history, on_step, save_observation)
        self._call_ids: deque[str] = deque()
        self._response_id: str | None = None

    async def run(self, request: str) -> str:
        limit_message = f"Shopper reached the {self.step_limit}-step limit"
        remaining = self.step_limit - self.steps
        if remaining <= 0:
            raise ShopperFailure(limit_message)
        self.history.append({"event": "request", "text": request})
        inputs = await self._request_input(request)
        try:
            async with AsyncOpenAI(max_retries=0, timeout=90) as client:
                # The SDK loops over model responses and computer actions until the shopper replies.
                result = await Runner.run(
                    self._agent(client),
                    inputs,
                    hooks=self,
                    run_config=RunConfig(trace_include_sensitive_data=False),
                    max_turns=remaining,
                    previous_response_id=self._response_id,
                    auto_previous_response_id=True,
                )
        except MaxTurnsExceeded as error:
            raise ShopperFailure(limit_message) from error
        except ModelRefusalError as error:
            raise ShopperFailure("Shopper declined the request") from error
        except ModelBehaviorError as error:
            raise self._model_failure(error) from error
        except APIStatusError as error:
            raise ModelUnavailable(
                f"OpenAI returned HTTP {error.status_code} ({_status_detail(error)}), "
                f"request {_redact_detail(str(error.request_id))}"
            ) from None
        except (OpenAIError, AgentsException) as error:
            raise ModelUnavailable(
                f"SDK runner could not complete request ({type(error).__name__})"
            ) from error
        self._response_id = result.last_response_id
        if not self._response_id:
            raise ModelUnavailable("SDK runner returned no conversation response ID")
        if not isinstance(result.final_output, str) or not result.final_output.strip():
            raise ShopperFailure("Shopper stopped without a final answer")
        answer = result.final_output.strip()
        self.history.append({"event": "answer", "step": self.steps, "text": answer})
        return answer

    def _agent(self, client: AsyncOpenAI) -> Agent[None]:
        return Agent(
            name="Storefront shopper",
            instructions=INSTRUCTIONS,
            model=OpenAIResponsesModel(self.model, client),
            model_settings=ModelSettings(
                max_tokens=MAX_OUTPUT_TOKENS,
                reasoning=Reasoning(effort=REASONING),
                store=True,
                # SDK-local evidence capture. This option does not change the API payload.
                preserve_raw_usage=True,
                # Use the same default prompt caching policy for both customer requests.
                extra_args={"prompt_cache_key": omit},
            ),
            # The response hook records flagged calls and stops the whole response. Also
            # require rejection at the computer boundary, where the SDK defaults to allowing.
            tools=[ComputerTool(computer=self.computer, on_safety_check=lambda _: False)],
        )

    async def _request_input(self, request: str) -> list[TResponseInputItem]:
        if self._response_id is not None:
            return [{"role": "user", "content": request}]
        image = "data:image/png;base64," + await self.computer.screenshot()
        return [
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": request},
                    {"type": "input_image", "detail": "original", "image_url": image},
                ],
            }
        ]

    async def on_llm_start(
        self,
        context: RunContextWrapper[None],
        agent: Agent[None],
        system_prompt: str | None,
        input_items: list[TResponseInputItem],
    ) -> None:
        if self.on_step:
            self.on_step()
        self.steps += 1
        self.computer.turn = self.steps

    async def on_llm_end(
        self, context: RunContextWrapper[None], agent: Agent[None], response: ModelResponse
    ) -> None:
        self.history.append(
            {
                "event": "response",
                "step": self.steps,
                "id": response.response_id,
                "request_id": response.request_id,
                "model": self.model,
                "status": "completed",
                "usage": token_counts(response.usage),
                "raw_usage": response.raw_usage,
            }
        )
        # Inspect the whole response before the SDK dispatches any computer action.
        for call in response.output:
            if call.type != "computer_call":
                continue
            if call.pending_safety_checks:
                self.history.append(
                    {
                        "event": "computer_call",
                        "step": self.steps,
                        "call_id": call.call_id,
                        "outcome": "blocked",
                        "pending_safety_checks": [
                            check.model_dump(exclude_none=True)
                            for check in call.pending_safety_checks
                        ],
                    }
                )
                raise ShopperFailure("Shopper action requires human review")
            if not call.actions:
                raise ShopperFailure("Computer call contained no computer actions")
            self._call_ids.append(call.call_id)

    async def on_tool_start(
        self, context: RunContextWrapper[None], agent: Agent[None], tool: Tool
    ) -> None:
        # The SDK dispatches computer calls serially in model output order.
        self.computer.call_id = self._call_ids.popleft()

    def _model_failure(self, error: ModelBehaviorError) -> ModelUnavailable | ShopperFailure:
        # Terminal API responses bypass on_llm_end, but their usage still counts.
        if "`response.failed`" in error.message:
            status = "failed"
        elif "`response.incomplete`" in error.message:
            status = "incomplete"
        else:
            return ShopperFailure("SDK could not process the shopper response")
        self.history.append(
            {
                "event": "response",
                "step": self.steps,
                "model": self.model,
                "status": status,
                "usage": token_counts(error._terminal_usage),
            }
        )
        if status == "failed":
            return ModelUnavailable("OpenAI returned a failed response")
        return ShopperFailure("Shopper response was incomplete")
