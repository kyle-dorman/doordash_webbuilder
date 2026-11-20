import base64
import json
import re
import struct
from collections.abc import Iterator
from dataclasses import asdict
from pathlib import Path

import pytest
from inspect_ai.model import (
    ChatMessage,
    ContentImage,
    GenerateConfig,
    ModelOutput,
    get_model,
)
from inspect_ai.tool import ToolChoice, ToolInfo
from test_storefront import write_sample_feed
from webbuilder_agent.builder import (
    DEFAULT_MODEL,
    IncompleteBuild,
    generate,
)
from webbuilder_agent.render import render
from webbuilder_shared.feed import load_store

MODEL = "mockllm/design"
MOOD_BOARD: dict[str, object] = {
    "title": "Rice steam and chili lacquer",
    "scene": "A red lacquer bento tray emerging through a cloud of warm rice steam.",
    "feed_cues": ["Bento", "Rice <small>", "Choose mild & sweet or <hot>."],
    "palette": [
        {"name": "Rice steam", "hex": "#FFF5DF"},
        {"name": "Chili lacquer", "hex": "#A62212"},
        {"name": "Charcoal ink", "hex": "#29231E"},
    ],
    "materials": "Glossy lacquer beside the matte surface of grains of rice.",
    "lettering": "Square, hand-painted strokes softened at the corners.",
}
CONCEPT = "Use a bento tray layout and a button that unfolds the mild and hot rice options."
HOME = """<main id="menu"><h1>{{ store.name }}</h1>
<button type="button" id="unfold">Unfold the tray</button>
<p id="rice-options" hidden>Mild or hot rice</p>
{% for section in store.sections %}
<section data-menu-section="{{ section.name }}"><h2>{{ section.name }}</h2>
{% for item in section.items %}
<article data-menu-item="{{ item.item_id }}">
<h3>{{ item.name }}</h3><span>{{ item.display_price }}</span>
{% if item.description %}<p>{{ item.description }}</p>{% endif %}
{% if item.image_url %}<img src="{{ item.image_url }}" alt="{{ item.name }}">{% endif %}
{{ add_button(item) }}</article>
{% endfor %}</section>{% endfor %}</main><a href="review.html">Review order</a>"""
CHECKOUT = "<h1>{{ store.name }}</h1>{{ review_markup('index.html#menu') }}"


SCRIPT = """document.querySelector('#unfold')?.addEventListener('click', () => {
    document.querySelector('#rice-options').hidden = false;
    document.body.style.backgroundColor = 'navy';
});"""


def snapshot(site: Path) -> dict[Path, bytes]:
    return {p.relative_to(site): p.read_bytes() for p in site.rglob("*") if p.is_file()}


def preview_images(message: ChatMessage) -> Iterator[bytes]:
    if isinstance(message.content, str):
        return
    for part in message.content:
        if isinstance(part, ContentImage):
            png = base64.b64decode(part.image.split(",", 1)[1])
            assert png.startswith(b"\x89PNG\r\n\x1a\n")
            assert struct.unpack_from(">II", png, 16) == (1280, 900)
            yield png


def test_preview_revision_and_submission(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    feed = write_sample_feed(tmp_path, with_photos=False)
    store = load_store(feed, "123")
    monkeypatch.setattr("webbuilder_agent.builder.RUNS", tmp_path)
    previous = tmp_path / "agent" / "previous" / "999" / "agent"
    previous.mkdir(parents=True)
    other_concept = "A handwritten chalkboard of shuffleable courses"
    (previous / "run.json").write_text(
        json.dumps({"status": "submitted", "store_id": "999", "design_direction": other_concept})
    )
    css = "body { background: white; }"
    calls: list[tuple[str, dict[str, object]]] = [
        ("mood_board", {**MOOD_BOARD, "palette": [{"name": "Chili", "hex": "scarlet"}]}),
        ("mood_board", MOOD_BOARD),
        # The first draft needs a design direction and a valid template.
        ("edit", {"filename": "index.html", "content": "Premature edit"}),
        ("design_direction", {"concept": CONCEPT}),
        ("edit", {"filename": "index.html", "content": HOME + "{{ unknown_value }}"}),
        ("edit", {"filename": "review.html", "content": CHECKOUT}),
        ("edit", {"filename": "style.css", "content": css}),
        ("edit", {"filename": "storefront.js", "content": SCRIPT}),
        ("preview", {}),
        ("edit", {"filename": "index.html", "old_text": "{{ unknown_value }}", "content": ""}),
        ("preview", {"click": "#unfold"}),
        ("preview", {}),
        # Removing a description makes this preview ineligible for submission.
        ("edit", {"filename": "index.html", "old_text": "{{ item.description }}", "content": ""}),
        ("preview", {"click": "#unfold"}),
        ("submit", {}),
        # The corrected draft needs a fresh preview and a successful interaction.
        ("edit", {"filename": "index.html", "content": HOME}),
        ("edit", {"filename": "style.css", "old_text": "white", "content": "gold"}),
        ("submit", {}),  # Stale preview.
        ("preview", {}),
        ("submit", {}),  # Current revision has only been previewed at rest.
        ("preview", {"click": "#missing-control"}),
        ("preview", {"click": "#unfold"}),
        ("submit", {}),
    ]
    steps = enumerate(calls)
    preview_id = ""
    images: list[bytes] = []
    seen_errors: list[str] = []

    def respond(
        messages: list[ChatMessage],
        tools: list[ToolInfo],
        choice: ToolChoice,
        config: GenerateConfig,
    ) -> ModelOutput:
        nonlocal preview_id
        turn, (name, args) = next(steps)
        available = {tool.name for tool in tools}
        if turn in (0, 1):
            assert available == {"mood_board"}
            assert config.reasoning_effort == "high"
            assignment = next(message.text for message in messages if message.role == "user")
            assert other_concept not in assignment
            mood_brief, feed_json = assignment.split("Restaurant feed:\n", 1)
            assert json.loads(feed_json) == json.loads(json.dumps(asdict(store)))
            assert "mood board" in mood_brief.lower()
            if turn == 0:
                first_input = "\n".join(message.text for message in messages).lower()
                for later_concept in ("storefront", "checkout", "layout", "javascript", "jinja"):
                    assert later_concept not in first_input
            assert not list(tmp_path.rglob("mood-board.json"))
        elif turn == 2:
            assert available == {"design_direction", "edit", "preview", "submit"}
            handoff = next(message.text for message in reversed(messages) if message.role == "user")
            site_brief, board_json = handoff.split("Your mood board:\n", 1)
            assert "storefront.js" in site_brief and "review_markup" in site_brief
            assert json.loads(board_json) == MOOD_BOARD
            (board_path,) = tmp_path.rglob("mood-board.json")
            assert json.loads(board_path.read_text()) == MOOD_BOARD
            progress = json.loads(board_path.with_name("run.json").read_text())
            assert progress["mood_board"] == MOOD_BOARD
            assert progress["status"] == "incomplete"

        # Inspect can put the screenshot in a user message immediately after the tool reply.
        for message in messages[-2:]:
            if message.role == "tool" and message.error:
                seen_errors.append(message.error.message)
            if match := re.search(r"Preview ID: ([0-9a-f]+)", message.text):
                preview_id = match[1]
        images.extend(preview_images(messages[-1]))
        if name == "submit":
            args = {
                "preview_id": preview_id,
                "assessment": "Adjusted the background after preview.",
            }
        return ModelOutput.for_tool_call(MODEL, name, args)

    model = get_model(MODEL, custom_outputs=respond, memoize=False)
    # The final permitted assistant message submits. Its tool receipt hits Inspect's limit.
    index = generate(
        feed,
        "123",
        model=model,
        message_limit=2 * len(calls) + 2,
    )
    output = index.parent
    evidence = output.parent / "agent"
    report = json.loads((evidence / "run.json").read_text())
    assert report["status"] == "submitted"
    assert (evidence / report["inspect_log"]).is_file()
    assert report["limit"]["type"] == "message"
    assert DEFAULT_MODEL == "openai/gpt-6.1-terra"
    assert report["reasoning_effort"] == "high"
    assert report["mood_board"] == MOOD_BOARD
    assert json.loads((evidence / "mood-board.json").read_text()) == MOOD_BOARD
    assert report["design_direction"] == CONCEPT

    expected_errors = [
        "#RRGGBB",
        "design_direction",
        "unknown_value",
        "item 100 is missing its full description",
        "current draft",
        "custom interaction",
        "#missing-control",
    ]
    for expected, actual in zip(expected_errors, seen_errors, strict=True):
        assert expected in actual

    previews = report["previews"]
    assert [p["click"] for p in previews] == ["#unfold", None, "#unfold", None, "#unfold"]
    assert report["submitted_preview"] == previews[-1]["image"]
    assert images == [(evidence / p["image"]).read_bytes() for p in previews]
    first_open, first_home, _, final_home, final_open = images
    assert first_open == final_open  # JavaScript reveals the same navy tray in both revisions.
    assert len({first_open, first_home, final_home}) == 3
    assert (evidence / "first.png").read_bytes() == first_home
    assert (evidence / "final.png").read_bytes() == final_home
    assert index.name == "index.html" and output.name == "submitted"
    for source, site, color in [
        ("first-source", evidence / "first", "white"),
        ("submitted-source", output, "gold"),
    ]:
        files = {p.name: p.read_text() for p in (evidence / source).iterdir()}
        assert files["style.css"] == css.replace("white", color)
        assert files["storefront.js"] == SCRIPT
        rebuilt = tmp_path / ("rebuilt-" + color)
        rebuilt.mkdir()
        render(store, files, rebuilt)
        assert snapshot(site) == snapshot(rebuilt)


def test_render_saved_design_without_custom_script(tmp_path: Path) -> None:
    feed = write_sample_feed(tmp_path, with_photos=False)
    site = tmp_path / "legacy-site"
    render(
        load_store(feed, "123"),
        {"index.html": HOME, "review.html": CHECKOUT, "style.css": "body { color: black }"},
        site,
    )
    for page in (site / "index.html", site / "review.html"):
        html = page.read_text()
        assert 'src="assets/cart.js"' in html
        assert "storefront.js" not in html


def test_message_budget_cannot_publish_an_unsubmitted_build(tmp_path: Path) -> None:
    feed = write_sample_feed(tmp_path, with_photos=False)
    model = get_model(MODEL, memoize=False)
    with pytest.raises(IncompleteBuild, match="No preview was submitted"):
        generate(feed, "123", tmp_path / "site", model=model, message_limit=3)
    report = json.loads((tmp_path / "site-evidence" / "run.json").read_text())
    assert report["status"] == "incomplete" and report["limit"]["type"] == "message"
    assert report["mood_board"] is None and not report["previews"]
    assert not (tmp_path / "site-evidence" / "mood-board.json").exists()
    assert not (tmp_path / "site").exists()
