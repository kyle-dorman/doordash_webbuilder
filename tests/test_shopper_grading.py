from dataclasses import replace

import pytest
from webbuilder_shopper.computer_use.answers import grade_lookup_answer
from webbuilder_shopper.grading import (
    RICE,
    ROLLS,
    TEA,
    GradeError,
    ReceiptLine,
    grade_checkout,
    grade_contact,
    grade_hours,
    grade_initial_cart,
    grade_soup,
    grade_submissions,
)

# Representative source-feed names including section numbering and dietary/size labels.
MENU_NAMES = [
    "10. Tom-Yum Soup (GF)",
    "11. Tom-Kha (GF)",
    "17.1. Pad Thai & Salmon",
    RICE,
    TEA,
]


def test_lookup_grading_accepts_equivalent_formats() -> None:
    grade_contact("219 Southwest 9th Avenue\nPortland, OR 97205", "+1 503.719.7273")
    grade_hours("11:30 – 21:15", "11 a.m. to 9:45 p.m.")
    grade_soup("24-ounce hot and sour soup", "14.5 USD")


@pytest.mark.parametrize(
    ("story", "answer"),
    [
        ("contact", "Phone: +1 503.719.7273.\nAddress: 219 SW 9th Ave., Portland, Oregon 97205."),
        ("contact", "**219 Southwest 9th Avenue**\nPortland, OR 97205\n(503) 719-7273"),
        ("hours", "On Friday they open at 11 a.m. and close at 9:45 p.m.; Tuesday is 11:30–21:15."),
        ("hours", "| Tuesday | 11:30 AM | 9:15 PM |\n| Friday | 11 AM | 9:45 PM |"),
        ("hours", "Tuesday closes at 9:15 PM and opens at 11:30 AM. Friday 11–21:45."),
        ("soup", "The **Tom-Yum Soup** comes in a 24-ounce portion and costs **$14.50**."),
        ("soup", "Tom-Yum Soup is 24 oz and costs $14.50."),
        ("soup", "The Tom Yum Soup is served in a 24 oz bowl. Its price is 14.50 USD."),
        ("soup", "Size: 24 oz\nPrice: $14.50"),
        ("soup", "It’s a 24 oz serving and costs about $14.50."),
        (
            "soup",
            "According to the menu, the Tom-Yum Soup (GF) comes in a 24 oz portion "
            "and costs $14.50.",
        ),
        ("soup", "14,50 USD for 24 fl. oz."),
        ("soup", "24 oz, 14.5"),
    ],
)
def test_shopper_final_answer_accepts_correct_prose(story: str, answer: str) -> None:
    grade_lookup_answer(story, answer, menu_names=MENU_NAMES)


@pytest.mark.parametrize(
    ("story", "answer"),
    [
        ("contact", "The address is 1219 Southwest 9th Avenue, Portland OR 97205. (503) 719-7273"),
        ("contact", "219 Southwest 9th Avenue Portland OR 97205. (503) 719-72730"),
        ("hours", "Friday 11:30 AM–9:15 PM, Tuesday 11 AM–9:45 PM."),
        ("hours", "Tuesday closes at 11:30 AM and opens at 9:15 PM. Friday 11–21:45."),
        ("hours", "Tuesday 11:30 AM–9:15 PM."),
        ("soup", "24 oz, $114.50"),
        ("soup", "124 oz, $14.50"),
        ("soup", "24 oz, $14,500"),
        ("soup", "24 oz, $14.50 or $18.50."),
        ("soup", "24 oz, perhaps 12 oz, $14.50"),
        ("soup", "Tom-Kha Soup is 24 oz and costs $14.50."),
        ("soup", "The clam chowder is 24 oz and costs $14.50."),
        ("soup", "Tom-Yum Soup is sold out. Clam chowder is 24 oz and costs $14.50."),
        ("soup", "tom yum soup is unavailable. pad thai is 24 oz and costs $14.50."),
        ("soup", "The Tom-Yum Soup is unavailable. The Tom Kha Soup is 24 oz and costs $14.50."),
        ("soup", "Tom-Yum Soup is 24 oz. The price of the rice is $14.50."),
        ("soup", "24 oz for $14.50 for Thai lime tea, not Tom-Yum."),
    ],
)
def test_shopper_final_answer_rejects_wrong_or_ambiguous_facts(story: str, answer: str) -> None:
    with pytest.raises(GradeError):
        grade_lookup_answer(story, answer, menu_names=MENU_NAMES)


@pytest.mark.parametrize("story", ["contact", "hours", "soup"])
def test_each_lookup_rejects_even_an_unsuccessful_submission(story: str) -> None:
    grade_submissions(story, [])
    with pytest.raises(GradeError, match="zero order submissions"):
        grade_submissions(story, [None])


def test_contact_and_hours_need_the_correct_complete_values() -> None:
    with pytest.raises(GradeError, match="address"):
        grade_contact("219 9th Avenue, Portland, OR 97205", "5037197273")
    with pytest.raises(GradeError, match="phone"):
        grade_contact("219 Southwest 9th Avenue Portland OR 97205", "50371972730")
    with pytest.raises(GradeError, match="Tuesday"):
        grade_hours("11 AM–9:45 PM", "11:30 AM–9:15 PM")
    with pytest.raises(GradeError, match="Friday"):
        grade_hours("11:30 AM–9:15 PM", "11 PM–9:45 PM")


@pytest.mark.parametrize(
    ("size", "price"),
    [("124 oz", "$14.50"), ("24 oz", "$114.50"), ("24 oz", "$14,500"), ("24 oz", "$14.501")],
)
def test_menu_grading_checks_complete_size_and_price(size: str, price: str) -> None:
    with pytest.raises(GradeError):
        grade_soup(size, price)


def test_edit_checkpoint_needs_exactly_one_of_each_visible_item() -> None:
    grade_initial_cart([(RICE, 1), (TEA, 1)], 0)
    with pytest.raises(GradeError, match="before the cart change"):
        grade_initial_cart([(RICE, 1), (TEA, 1)], 1)
    for wrong in ([(TEA, 2)], [(TEA, 2), (RICE, 1)], [(TEA, 1), (RICE, 1), (RICE, 1)]):
        with pytest.raises(GradeError, match="in the cart"):
            grade_initial_cart(wrong, 0)


def test_confirmation_and_mock_must_independently_match_the_order() -> None:
    tea = ReceiptLine(TEA, 2, "$4.50", "$9")
    item = {
        "item_id": "548484849",
        "name": TEA,
        "quantity": 2,
        "unit_price_cents": 450,
        "line_total_cents": 900,
    }
    order: dict[str, object] = {"store_id": "265151", "items": [item], "subtotal_cents": 900}
    grade_checkout("change", [tea], "USD 9.00")
    grade_submissions("change", [order])
    bad_submissions: list[list[dict[str, object] | None]] = [
        [],
        [None],
        [order, order],
        [None, order],
    ]
    for submissions in bad_submissions:
        with pytest.raises(GradeError, match="one accepted mock submission"):
            grade_submissions("change", submissions)
    for wrong_order in (
        order | {"store_id": "other"},
        order | {"subtotal_cents": 90},
        order | {"items": [item | {"item_id": "140247117"}]},
        order | {"items": [item | {"quantity": 1}]},
    ):
        with pytest.raises(GradeError, match="mock"):
            grade_submissions("change", [wrong_order])
    for lines in (
        [replace(tea, name=RICE)],
        [replace(tea, quantity=1)],
        [replace(tea, unit_price="$9")],
        [replace(tea, line_total="$4.50")],
        [tea, tea],
    ):
        with pytest.raises(GradeError):
            grade_checkout("change", lines, "$9")
    with pytest.raises(GradeError, match="confirmation total"):
        grade_checkout("change", [tea], "$4.50")


def test_place_order_allows_items_in_either_display_order() -> None:
    rolls = ReceiptLine(ROLLS, 2, "$8.5", "$17")
    rice = ReceiptLine(RICE, 1, "$2.50", "2.50 USD")
    order: dict[str, object] = {
        "store_id": "265151",
        "subtotal_cents": 1950,
        "items": [
            {
                "item_id": "140247117",
                "name": RICE,
                "quantity": 1,
                "unit_price_cents": 250,
                "line_total_cents": 250,
            },
            {
                "item_id": "140240246",
                "name": ROLLS,
                "quantity": 2,
                "unit_price_cents": 850,
                "line_total_cents": 1700,
            },
        ],
    }
    grade_checkout("place", [rolls, rice], "$19.50")
    grade_submissions("place", [order])
