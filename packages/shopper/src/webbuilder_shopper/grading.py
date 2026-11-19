"""Grade Thai Peacock shopper evidence against the agreed roadmap outcomes."""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

type Submissions = Sequence[dict[str, object] | None]

STORE_ID = "265151"
STORIES = {
    "contact": "Contact details",
    "hours": "Posted hours",
    "soup": "Menu lookup",
    "place": "Place an order",
    "change": "Change an order",
}
ROLLS = "3. Vegan Crispy Spring Rolls (4) (VG)"
RICE = "Rice (16oz.)"
TEA = "Thai Lime Tea"


class GradeError(ValueError):
    """The shopper's evidence does not meet the agreed outcome."""


@dataclass(frozen=True)
class ReceiptLine:
    """Values read from a single visible confirmation line."""

    name: str
    quantity: int
    unit_price: str
    line_total: str


@dataclass(frozen=True)
class _OrderLine:
    item_id: str
    name: str
    quantity: int
    unit_price_cents: int

    @property
    def line_total_cents(self) -> int:
        return self.quantity * self.unit_price_cents


_ORDERS: dict[str, tuple[_OrderLine, ...]] = {
    "place": (_OrderLine("140240246", ROLLS, 2, 850), _OrderLine("140247117", RICE, 1, 250)),
    "change": (_OrderLine("548484849", TEA, 2, 450),),
}

SIZE_PATTERN = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)[\s-]*(?:fl\.?\s*)?(?:oz|ounces?)\b", re.I)


def grade_contact(address: str, phone: str) -> None:
    street = " ".join(re.findall(r"\w+", address.casefold()))
    if not re.fullmatch(r"219 (southwest|sw) 9th (avenue|ave) portland (or|oregon) 97205", street):
        raise GradeError(f"Incorrect address: {address!r}")
    digits = re.sub(r"[\s().-]", "", phone)
    if not re.fullmatch(r"(?:\+?1)?5037197273", digits):
        raise GradeError(f"Incorrect phone number: {phone!r}")


def _minutes(clock: str) -> int:
    match = re.fullmatch(
        r"(\d{1,2})(?::([0-5]\d))?\s*(?:([ap])\.?\s*m\.?)?", clock.strip().casefold()
    )
    if not match:
        raise GradeError(f"Unrecognized time: {clock!r}")
    hour = int(match[1])
    if match[3]:
        if not 1 <= hour <= 12:
            raise GradeError(f"Invalid 12-hour time: {clock!r}")
        hour = hour % 12 + (12 if match[3] == "p" else 0)
    elif hour > 23:
        raise GradeError(f"Invalid 24-hour time: {clock!r}")
    return 60 * hour + int(match[2] or 0)


def grade_hours(tuesday: str, friday: str) -> None:
    for day, interval, opens, closes in (
        ("Tuesday", tuesday, 11 * 60 + 30, 21 * 60 + 15),
        ("Friday", friday, 11 * 60, 21 * 60 + 45),
    ):
        times = re.split(r"\s*(?:[-–—−]|\bto\b|\buntil\b)\s*", interval, flags=re.I)
        if len(times) != 2 or (_minutes(times[0]), _minutes(times[1])) != (opens, closes):
            raise GradeError(f"Incorrect {day} hours: {interval!r}")


def _check_price(label: str, text: str, cents: int) -> None:
    # Compare the entire amount to avoid accepting a rounded price or a substring of another one.
    amount = re.fullmatch(
        r"\s*(?:USD\s*)?\$?\s*(\d+(?:\.\d+|,\d{1,2})?)\s*(?:USD|dollars?)?\s*", text, re.I
    )
    expected = Decimal(cents).scaleb(-2)
    if not amount or Decimal(amount[1].replace(",", ".")) != expected:
        raise GradeError(f"{label}: expected ${expected:.2f}, saw {text!r}")


def grade_soup(size: str, price: str) -> None:
    sizes = SIZE_PATTERN.findall(size)
    if not sizes or any(Decimal(value) != 24 for value in sizes):
        raise GradeError(f"Incorrect Tom-Yum Soup size: {size!r}")
    _check_price("Tom-Yum Soup price", price, 1450)


def _name(text: str) -> str:
    return " ".join(text.casefold().split())


def grade_initial_cart(lines: Sequence[tuple[str, int]], submission_count: int) -> None:
    """Check every visible cart line before the edit story may proceed."""
    actual = sorted((_name(name), quantity) for name, quantity in lines)
    if actual != sorted([(_name(TEA), 1), (_name(RICE), 1)]):
        raise GradeError(
            f"Expected one Thai Lime Tea and one 16 oz rice in the cart, saw {lines!r}"
        )
    if submission_count:
        raise GradeError("Order submitted before the cart change request.")


def grade_submissions(story: str, submissions: Submissions) -> None:
    """Grade the mock's complete record for this attempt, including rejections."""
    if story in ("contact", "hours", "soup"):
        if submissions:
            raise GradeError(f"Expected zero order submissions, saw {len(submissions)}.")
        return
    expected = _ORDERS[story]
    if len(submissions) != 1 or submissions[0] is None:
        accepted = sum(order is not None for order in submissions)
        raise GradeError(
            f"Expected exactly one accepted mock submission, saw {len(submissions)} "
            f"submissions ({accepted} accepted)."
        )
    order = submissions[0]
    subtotal = sum(line.line_total_cents for line in expected)
    if order.get("store_id") != STORE_ID or order.get("subtotal_cents") != subtotal:
        raise GradeError(f"Incorrect mock store or subtotal: {order!r}")
    items = order.get("items")
    if not isinstance(items, list) or len(items) != len(expected):
        raise GradeError(f"Incorrect mock order items: {items!r}")
    for line in expected:
        confirmed = {
            "item_id": line.item_id,
            "name": line.name,
            "quantity": line.quantity,
            "unit_price_cents": line.unit_price_cents,
            "line_total_cents": line.line_total_cents,
        }
        if confirmed not in items:
            raise GradeError(f"Expected {confirmed!r} in the mock order, saw {items!r}")


def grade_checkout(story: str, lines: Sequence[ReceiptLine], total: str) -> None:
    """Grade the names, quantities and amounts actually shown in the confirmation."""
    expected = _ORDERS[story]
    by_name = {_name(line.name): line for line in expected}
    if sorted(_name(visible.name) for visible in lines) != sorted(by_name):
        raise GradeError(f"Incorrect dishes in visible confirmation: {lines!r}")
    for visible in lines:
        dish = by_name[_name(visible.name)]
        if visible.quantity != dish.quantity:
            raise GradeError(
                f"{dish.name}: expected quantity {dish.quantity}, saw {visible.quantity}"
            )
        _check_price(f"{dish.name} unit price", visible.unit_price, dish.unit_price_cents)
        _check_price(f"{dish.name} line total", visible.line_total, dish.line_total_cents)
    _check_price(
        "Visible confirmation total", total, sum(line.line_total_cents for line in expected)
    )
