"""The viewport and in-page actions exposed to the SDK ComputerTool."""

import base64
from collections.abc import Callable, Iterator
from contextlib import contextmanager

from agents import AsyncComputer, Button
from openai.types.responses import computer_action as actions
from playwright.async_api import Error, Page, ViewportSize

VIEWPORT: ViewportSize = {"width": 1280, "height": 900}
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


class PlaywrightComputer(AsyncComputer):
    """Execute the SDK's in-page actions and record the viewport it receives."""

    def __init__(
        self,
        page: Page,
        history: list[dict[str, object]],
        on_step: Callable[[], None] | None,
        save_observation: Callable[[bytes], str] | None,
    ) -> None:
        self.page = page
        self.history = history
        self.on_step = on_step
        self.save_observation = save_observation
        # The SDK hooks set these before dispatch so evidence identifies its model turn and call.
        self.turn = 0
        self.call_id: str | None = None

    @contextmanager
    def _action(self, action: actions.ComputerAction) -> Iterator[None]:
        if self.on_step:
            self.on_step()
        event: dict[str, object] = {
            "event": "action",
            "step": self.turn,
            "call_id": self.call_id,
            "action": action.model_dump(exclude_none=True),
        }
        self.history.append(event)
        try:
            if action.type in ("click", "double_click", "move", "scroll"):
                if action.keys:
                    raise ShopperFailure("Modified pointer actions are unavailable")
                if not (0 <= action.x < VIEWPORT["width"] and 0 <= action.y < VIEWPORT["height"]):
                    raise ShopperFailure(
                        f"Shopper targeted a point outside the viewport: {action.x, action.y}"
                    )
            yield
        except (ShopperFailure, Error) as error:
            event["outcome"] = "blocked" if isinstance(error, ShopperFailure) else "error"
            event["reason"] = str(error)
            raise
        event["outcome"] = "executed"

    async def screenshot(self) -> str:
        if self.call_id is not None:
            # Allow the viewport to settle after the model's batch of actions.
            await self.page.wait_for_timeout(250)
        png = await self.page.screenshot(type="png", scale="css")
        path = self.save_observation(png) if self.save_observation else None
        self.history.append(
            {"event": "screenshot", "step": self.turn, "call_id": self.call_id, "screenshot": path}
        )
        return base64.b64encode(png).decode("ascii")

    async def click(self, x: int, y: int, button: Button, *, keys: list[str] | None = None) -> None:
        with self._action(actions.Click(type="click", x=x, y=y, button=button, keys=keys)):
            if button != "left":
                raise ShopperFailure(f"Unavailable shopper mouse button: {button}")
            await self.page.mouse.click(x, y)

    async def double_click(self, x: int, y: int, *, keys: list[str] | None = None) -> None:
        with self._action(actions.DoubleClick(type="double_click", x=x, y=y, keys=keys)):
            await self.page.mouse.dblclick(x, y)

    async def move(self, x: int, y: int, *, keys: list[str] | None = None) -> None:
        with self._action(actions.Move(type="move", x=x, y=y, keys=keys)):
            await self.page.mouse.move(x, y)

    async def scroll(
        self, x: int, y: int, scroll_x: int, scroll_y: int, *, keys: list[str] | None = None
    ) -> None:
        with self._action(
            actions.Scroll(type="scroll", x=x, y=y, scroll_x=scroll_x, scroll_y=scroll_y, keys=keys)
        ):
            await self.page.mouse.move(x, y)
            await self.page.mouse.wheel(scroll_x, scroll_y)

    async def drag(self, path: list[tuple[int, int]], *, keys: list[str] | None = None) -> None:
        with self._action(
            actions.Drag(type="drag", path=[actions.DragPath(x=x, y=y) for x, y in path], keys=keys)
        ):
            raise ShopperFailure("Unavailable shopper action: drag")

    async def keypress(self, keys: list[str]) -> None:
        with self._action(actions.Keypress(type="keypress", keys=keys)):
            if len(keys) != 1 or keys[0].lower() not in _PAGE_KEYS:
                raise ShopperFailure(f"Unavailable shopper keypress: {keys}")
            await self.page.keyboard.press(_PAGE_KEYS[keys[0].lower()])

    async def type(self, text: str) -> None:
        with self._action(actions.Type(type="type", text=text)):
            await self.page.keyboard.insert_text(text)

    async def wait(self) -> None:
        with self._action(actions.Wait(type="wait")):
            await self.page.wait_for_timeout(500)
