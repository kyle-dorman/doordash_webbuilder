"""Grade Thai Peacock shopper evidence against the agreed roadmap outcomes."""

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

type Submissions = Sequence[dict[str, object] | None]
type CheckoutStory = Literal["place", "change"]

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

_SIZE = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)[\s-]*(?:fl\.?\s*)?(?:oz|ounces?)\b", re.I)
_IMPLIED_SUBJECT_WORDS = frozenset(
    "size price cost costs priced listed serving portion bowl it its s the this soup a an "
    "is comes served in at for of and each per".split()
)


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
    sizes = _SIZE.findall(size)
    if not sizes or any(Decimal(value) != 24 for value in sizes):
        raise GradeError(f"Incorrect Tom-Yum Soup size: {size!r}")
    _check_price("Tom-Yum Soup price", price, 1450)


def _single(label: str, values: list[str]) -> str:
    if len(values) != 1:
        raise GradeError(f"Expected one {label} in the shopper's final answer, saw {values!r}")
    return values[0]


def _answer_interval(day: str, text: str) -> str | None:
    times = re.findall(
        r"(?:\b(open(?:s|ing)?|clos(?:es?|ing))\s*(?:(?:time|is|at|from)\s+)*[:|]?\s*)?"
        r"(?<![\w:])(\d{1,2}(?::\d{2})?(?:\s*[ap]\.?\s*m\.?)?)(?![\w:])",
        text,
        re.I,
    )
    if not times:
        return None
    if len(times) != 2:
        raise GradeError(f"Expected opening and closing times for {day}, saw {text!r}")
    (first_role, first), (second_role, second) = times
    roles = (first_role.lower()[:1], second_role.lower()[:1])
    if roles[0] and roles[0] == roles[1]:
        raise GradeError(f"Ambiguous opening and closing times for {day}: {text!r}")
    if roles[0] == "c" or roles[1] == "o":
        first, second = second, first
    return f"{first}–{second}"


def _check_soup_subject(answer: str, price: str, menu_names: Iterable[str]) -> None:
    """Keep facts for another menu entry from satisfying the Tom-Yum lookup."""
    words = " " + " ".join(re.findall(r"\w+", answer.casefold())) + " "
    for name in menu_names:
        # Match names as shoppers write them, omitting menu numbers and parenthesized labels.
        base = re.sub(r"^\s*(?:\d+\.\s*)+|\([^)]*\)", "", name).casefold()
        # Compound entries such as "Pad Thai & Salmon" may be called simply "Pad Thai".
        base = base.partition(" & ")[0]
        dish = " ".join(re.findall(r"\w+", base))
        if dish and dish != "tom yum soup" and f" {dish} " in words:
            raise GradeError(f"Tom-Yum Soup answer names another menu item {name!r}: {answer!r}")

    # A bare answer ("24 oz, $14.50") inherits the question's subject. Longer prose
    # should name the dish in the sentence that supplies the facts.
    facts = _SIZE.sub(" § ", answer).replace(price, " § ")
    for clause in re.split(r"[;!?\n]+|\.(?:\s+|$)", facts):
        if "§" not in clause or re.search(r"\btom[\s‐‑‒–—-]*yum\b", clause, re.I):
            continue
        if set(re.findall(r"[^\W\d_]+", clause.casefold())) - _IMPLIED_SUBJECT_WORDS:
            raise GradeError(f"Cannot attribute this size or price to Tom-Yum Soup: {answer!r}")


def grade_lookup_answer(story: str, answer: str, *, menu_names: Iterable[str] = ()) -> None:
    """Extract facts from the shopper's final text and apply the scripted runner's graders."""
    plain = re.sub(r"[*_`]", "", answer)
    if story == "contact":
        # A numbered street, city and state followed by a ZIP (also accepts multiline addresses).
        addresses = re.findall(
            r"\b\d+\s+(?:[\w.-]+\s+){1,7}(?:ave(?:nue)?|st(?:reet)?|rd|road|blvd)\b"
            r"[.,\s]+[a-z]+(?:\s+[a-z]+)*?[,\s]+[a-z]+\s+\d{5}(?:-\d{4})?\b",
            plain,
            re.I,
        )
        phones = re.findall(
            r"(?<!\w)(?:\+?\d{1,3}[\s.-]*)?\(?\d{3}\)?[\s.-]*\d{3}[\s.-]*\d{4}(?!\w)", plain
        )
        grade_contact(_single("address", addresses), _single("phone number", phones))
    elif story == "hours":
        # Keep day associations, including reordered answers, bullet lists and Markdown tables.
        sections = re.split(r"\b(tue(?:s(?:day)?)?|fri(?:day)?)\b", plain, flags=re.I)
        intervals: dict[str, list[str]] = {"tue": [], "fri": []}
        for day, segment in zip(sections[1::2], sections[2::2], strict=True):
            interval = _answer_interval(day, segment)
            if interval:
                intervals[day.lower()[:3]].append(interval)
        grade_hours(
            _single("Tuesday interval", intervals["tue"]),
            _single("Friday interval", intervals["fri"]),
        )
    elif story == "soup":
        # A prefixed/suffixed price is unambiguous even if the dish also has a menu number.
        remaining = _SIZE.sub("", plain)
        number = r"\d+(?:[.,]\d+)*"
        prices = re.findall(
            rf"(?:\$|\bUSD\s*\$?)\s*{number}(?:\s*(?:USD|dollars?)\b)?"
            rf"|(?<![\w.,]){number}\s*(?:USD|dollars?)\b",
            remaining,
            re.I,
        )
        if not prices:
            prices = re.findall(rf"(?<![\w.,]){number}(?!\w)", remaining)
        price = _single("Tom-Yum Soup price", prices)
        grade_soup(plain, price)
        _check_soup_subject(plain, price, menu_names)
    else:
        raise GradeError(f"Unknown lookup story {story!r}")


def _name(text: str) -> str:
    return " ".join(text.casefold().split())


def grade_initial_cart(lines: Sequence[tuple[str, int]]) -> None:
    """Check every visible cart line before the edit story may proceed."""
    actual = sorted((_name(name), quantity) for name, quantity in lines)
    if actual != sorted([(_name(TEA), 1), (_name(RICE), 1)]):
        raise GradeError(
            f"Expected one Thai Lime Tea and one 16 oz rice in the cart, saw {lines!r}"
        )


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


def grade_checkout(story: CheckoutStory, lines: Sequence[ReceiptLine], total: str) -> None:
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
