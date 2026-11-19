"""Run the Agents SDK computer shopper against the harness's restricted Playwright page."""

import asyncio
import base64
from collections import deque
from collections.abc import Callable
from concurrent.futures import Future
from queue import SimpleQueue

from agents import (
    Agent,
    AgentsException,
    AsyncComputer,
    Button,
    ComputerTool,
    MaxTurnsExceeded,
    ModelBehaviorError,
    ModelRefusalError,
    ModelResponse,
    ModelSettings,
    OpenAIResponsesModel,
    RunContextWrapper,
    RunHooks,
    Runner,
    Tool,
    TResponseInputItem,
    trace,
)
from anyio.from_thread import start_blocking_portal
from openai import APIStatusError, AsyncOpenAI, OpenAIError, omit
from openai.types.responses import computer_action as actions
from openai.types.shared import Reasoning
from playwright.sync_api import Page

from .computer_model import (
    INSTRUCTIONS,
    MAX_OUTPUT_TOKENS,
    REASONING,
    ModelUnavailable,
    ShopperFailure,
    _status_detail,
    check_safety,
    execute_action,
)
from .shopper_usage import token_counts


class _PageComputer(AsyncComputer):
    """Dispatch SDK operations to the thread that owns the synchronous Playwright page."""

    def __init__(self, session: "SdkShopperSession", page: Page) -> None:
        self.session = session
        self.page = page
        self.operations: SimpleQueue[Callable[[], None] | None] = SimpleQueue()
        self.call_id = ""

    async def on_page[T](self, function: Callable[[], T]) -> T:
        result: Future[T] = Future()

        def perform() -> None:
            if result.set_running_or_notify_cancel():
                try:
                    result.set_result(function())
                except Exception as error:
                    result.set_exception(error)

        self.operations.put(perform)
        return await asyncio.wrap_future(result)

    async def _act(self, action: actions.ComputerAction) -> None:
        def perform() -> None:
            if self.session.on_step:
                self.session.on_step()
            execute_action(
                self.page, action, self.session.history, self.session.steps, self.call_id
            )

        await self.on_page(perform)

    async def screenshot(self) -> str:
        def capture() -> str:
            self.page.wait_for_timeout(250)
            return self.session.capture(self.page, self.call_id)

        return await self.on_page(capture)

    async def click(self, x: int, y: int, button: Button, *, keys: list[str] | None = None) -> None:
        await self._act(actions.Click(type="click", x=x, y=y, button=button, keys=keys))

    async def double_click(self, x: int, y: int, *, keys: list[str] | None = None) -> None:
        await self._act(actions.DoubleClick(type="double_click", x=x, y=y, keys=keys))

    async def move(self, x: int, y: int, *, keys: list[str] | None = None) -> None:
        await self._act(actions.Move(type="move", x=x, y=y, keys=keys))

    async def scroll(
        self, x: int, y: int, scroll_x: int, scroll_y: int, *, keys: list[str] | None = None
    ) -> None:
        await self._act(
            actions.Scroll(type="scroll", x=x, y=y, scroll_x=scroll_x, scroll_y=scroll_y, keys=keys)
        )

    async def drag(self, path: list[tuple[int, int]], *, keys: list[str] | None = None) -> None:
        await self._act(
            actions.Drag(type="drag", path=[actions.DragPath(x=x, y=y) for x, y in path], keys=keys)
        )

    async def keypress(self, keys: list[str]) -> None:
        await self._act(actions.Keypress(type="keypress", keys=keys))

    async def type(self, text: str) -> None:
        await self._act(actions.Type(type="type", text=text))

    async def wait(self) -> None:
        await self._act(actions.Wait(type="wait"))


class _AttemptHooks(RunHooks[None]):
    def __init__(self, session: "SdkShopperSession", computer: _PageComputer) -> None:
        self.session = session
        self.computer = computer
        self.call_ids: deque[str] = deque()

    async def on_llm_start(
        self,
        context: RunContextWrapper[None],
        agent: Agent[None],
        system_prompt: str | None,
        input_items: list[TResponseInputItem],
    ) -> None:
        if self.session.on_step:
            await self.computer.on_page(self.session.on_step)
        self.session.steps += 1

    async def on_llm_end(
        self, context: RunContextWrapper[None], agent: Agent[None], response: ModelResponse
    ) -> None:
        self.session.history.append(
            {
                "event": "response",
                "step": self.session.steps,
                "id": response.response_id,
                "request_id": response.request_id,
                "model": self.session.model,
                "status": "completed",
                "usage": token_counts(response.usage),
            }
        )
        # Inspect the whole response before the SDK dispatches any computer action.
        for call in response.output:
            if call.type == "computer_call":
                check_safety(call, self.session.history, self.session.steps)
                if not call.actions:
                    raise ShopperFailure("Computer call contained no native computer actions")
                self.call_ids.append(call.call_id)

    async def on_tool_start(
        self, context: RunContextWrapper[None], agent: Agent[None], tool: Tool
    ) -> None:
        # The SDK dispatches computer calls serially in model output order.
        self.computer.call_id = self.call_ids.popleft()


class SdkShopperSession:
    """The harness enters attempt_trace and calls run again only after grading the cart."""

    def __init__(self, model: str, step_limit: int, history: list[dict[str, object]]) -> None:
        self.model = model
        self.step_limit = step_limit
        self.history = history
        self.steps = 0
        self.on_step: Callable[[], None] | None = None
        self.save_observation: Callable[[bytes], str] | None = None
        self.last_screenshot: bytes | None = None
        self.attempt_trace = trace("Thai Peacock shopper", metadata={"model": model})
        if self.attempt_trace.export() is None:
            raise ModelUnavailable("Enable Agents SDK tracing to record the shopper attempt")
        self.trace_id = self.attempt_trace.trace_id
        self._response_id: str | None = None

    def capture(self, page: Page, call_id: str | None) -> str:
        self.last_screenshot = page.screenshot(type="png", scale="css")
        path = self.save_observation(self.last_screenshot) if self.save_observation else None
        self.history.append(
            {"event": "screenshot", "step": self.steps, "call_id": call_id, "screenshot": path}
        )
        return base64.b64encode(self.last_screenshot).decode("ascii")

    async def _shop(self, computer: _PageComputer, inputs: list[TResponseInputItem]) -> str:
        async with AsyncOpenAI(max_retries=0, timeout=90) as client:
            agent: Agent[None] = Agent(
                name="Storefront shopper",
                instructions=INSTRUCTIONS,
                model=OpenAIResponsesModel(self.model, client),
                model_settings=ModelSettings(
                    max_tokens=MAX_OUTPUT_TOKENS,
                    reasoning=Reasoning(effort=REASONING),
                    store=True,
                    # Keep the native request's default caching behavior across the edit handoff.
                    extra_args={"prompt_cache_key": omit},
                ),
                # The response hook records flagged calls and stops the whole response. Also
                # require rejection at the computer boundary, where the SDK defaults to allowing.
                tools=[ComputerTool(computer=computer, on_safety_check=lambda _: False)],
            )
            result = await Runner.run(
                agent,
                inputs,
                hooks=_AttemptHooks(self, computer),
                max_turns=self.step_limit - self.steps,
                previous_response_id=self._response_id,
                auto_previous_response_id=True,
            )
            self._response_id = result.last_response_id
            if not self._response_id:
                raise ModelUnavailable("SDK runner returned no conversation response ID")
            if not isinstance(result.final_output, str) or not result.final_output.strip():
                raise ShopperFailure("Shopper stopped without a final answer")
            return result.final_output.strip()

    def run(self, page: Page, request: str) -> str:
        self.history.append({"event": "request", "text": request})
        limit_message = f"Shopper reached the {self.step_limit}-step limit"
        if self.steps >= self.step_limit:
            raise ShopperFailure(limit_message)
        inputs: list[TResponseInputItem] = [{"role": "user", "content": request}]
        if self._response_id is None:
            image = "data:image/png;base64," + self.capture(page, None)
            inputs = [
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": request},
                        {"type": "input_image", "detail": "original", "image_url": image},
                    ],
                }
            ]
        computer = _PageComputer(self, page)
        try:
            # The portal propagates this attempt's trace into the SDK event loop. Only
            # this calling thread can service synchronous Playwright operations.
            with start_blocking_portal() as portal:
                finished = portal.start_task_soon(self._shop, computer, inputs)
                finished.add_done_callback(lambda _: computer.operations.put(None))
                while (operation := computer.operations.get()) is not None:
                    operation()
                answer = finished.result()
        except MaxTurnsExceeded as error:
            raise ShopperFailure(limit_message) from error
        except ModelRefusalError as error:
            raise ShopperFailure("Shopper declined the request") from error
        except ModelBehaviorError as error:
            # These terminal responses bypass the SDK's post-response hook.
            if "`response.failed`" in error.message or "`response.incomplete`" in error.message:
                failed = "`response.failed`" in error.message
                self.history.append(
                    {
                        "event": "response",
                        "step": self.steps,
                        "model": self.model,
                        "status": "failed" if failed else "incomplete",
                        "usage": token_counts(error._terminal_usage),
                    }
                )
                if failed:
                    raise ModelUnavailable("OpenAI returned a failed response") from error
                raise ShopperFailure("Shopper response was incomplete") from error
            raise ShopperFailure("SDK could not process the shopper response") from error
        except APIStatusError as error:
            raise ModelUnavailable(
                f"OpenAI returned HTTP {error.status_code} ({_status_detail(error)}), "
                f"request {error.request_id}"
            ) from error
        except (OpenAIError, AgentsException) as error:
            raise ModelUnavailable(
                f"SDK runner could not complete request ({type(error).__name__})"
            ) from error
        self.history.append({"event": "answer", "step": self.steps, "text": answer})
        return answer
