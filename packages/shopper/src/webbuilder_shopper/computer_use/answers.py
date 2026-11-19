"""Read lookup facts from the shopper’s final reply for private grading."""

import re
from collections.abc import Iterable

from ..grading import SIZE_PATTERN, GradeError, grade_contact, grade_hours, grade_soup

# A reply such as “It comes in a 24 oz bowl” inherits Tom-Yum from the question.
# Generic size and price wording can stand alone. Other dish names need checking.
_GENERIC_SIZE_AND_PRICE_WORDS = frozenset(
    "size price cost costs priced listed serving portion bowl it its s the this soup a an "
    "is comes served in at for of and each per about exactly".split()
)


def grade_lookup_answer(story: str, answer: str, *, menu_names: Iterable[str] = ()) -> None:
    """Extract facts from the shopper's final text and apply the shared graders."""
    plain = re.sub(r"[*_`]", "", answer)
    if story == "contact":
        _grade_contact_answer(plain)
    elif story == "hours":
        _grade_hours_answer(plain)
    elif story == "soup":
        _grade_soup_answer(plain, menu_names)
    else:
        raise GradeError(f"Unknown lookup story {story!r}")


def _single(label: str, values: list[str]) -> str:
    if len(values) != 1:
        raise GradeError(f"Expected one {label} in the shopper's final answer, saw {values!r}")
    return values[0]


def _grade_contact_answer(answer: str) -> None:
    # A numbered street, city and state followed by a ZIP (also accepts multiline addresses).
    addresses = re.findall(
        r"\b\d+\s+(?:[\w.-]+\s+){1,7}(?:ave(?:nue)?|st(?:reet)?|rd|road|blvd)\b"
        r"[.,\s]+[a-z]+(?:\s+[a-z]+)*?[,\s]+[a-z]+\s+\d{5}(?:-\d{4})?\b",
        answer,
        re.I,
    )
    phones = re.findall(
        r"(?<!\w)(?:\+?\d{1,3}[\s.-]*)?\(?\d{3}\)?[\s.-]*\d{3}[\s.-]*\d{4}(?!\w)", answer
    )
    grade_contact(_single("address", addresses), _single("phone number", phones))


def _grade_hours_answer(answer: str) -> None:
    # Keep day associations, including reordered answers, bullet lists and Markdown tables.
    sections = re.split(r"\b(tue(?:s(?:day)?)?|fri(?:day)?)\b", answer, flags=re.I)
    intervals: dict[str, list[str]] = {"tue": [], "fri": []}
    for day, segment in zip(sections[1::2], sections[2::2], strict=True):
        interval = _answer_interval(day, segment)
        if interval:
            intervals[day.lower()[:3]].append(interval)
    grade_hours(
        _single("Tuesday interval", intervals["tue"]),
        _single("Friday interval", intervals["fri"]),
    )


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
    first_role = first_role.lower()[:1]  # "o" for opening, "c" for closing, or absent.
    second_role = second_role.lower()[:1]
    if first_role and first_role == second_role:
        raise GradeError(f"Ambiguous opening and closing times for {day}: {text!r}")
    if first_role == "c" or second_role == "o":
        first, second = second, first
    return f"{first}–{second}"


def _grade_soup_answer(answer: str, menu_names: Iterable[str]) -> None:
    # A prefixed/suffixed price is unambiguous even if the dish also has a menu number.
    remaining = SIZE_PATTERN.sub("", answer)
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
    grade_soup(answer, price)
    _check_soup_subject(answer, price, menu_names)


def _check_soup_subject(answer: str, price: str, menu_names: Iterable[str]) -> None:
    """Keep facts for another menu entry from satisfying the Tom-Yum lookup."""
    normalized_answer = " " + " ".join(re.findall(r"\w+", answer.casefold())) + " "
    for name in menu_names:
        # Match names as shoppers write them, omitting menu numbers and parenthesized labels.
        base = re.sub(r"^\s*(?:\d+\.\s*)+|\([^)]*\)", "", name).casefold()
        # Compound entries such as "Pad Thai & Salmon" may be called simply "Pad Thai".
        base = base.partition(" & ")[0]
        dish = " ".join(re.findall(r"\w+", base))
        if dish and dish != "tom yum soup" and f" {dish} " in normalized_answer:
            raise GradeError(f"Tom-Yum Soup answer names another menu item {name!r}: {answer!r}")

    # Mask the values first so punctuation in a price or unit cannot split a fact.
    marker = "§"
    masked = SIZE_PATTERN.sub(marker, answer).replace(price, marker)
    for clause in re.split(r"[;!?\n]+|\.(?:\s+|$)", masked):
        if marker in clause and not re.search(r"\btom[\s‐‑‒–—-]*yum\b", clause, re.I):
            clause_words = set(re.findall(r"[^\W\d_]+", clause.casefold()))
            if not clause_words.issubset(_GENERIC_SIZE_AND_PRICE_WORDS):
                raise GradeError(f"Cannot attribute this size or price to Tom-Yum Soup: {answer!r}")
