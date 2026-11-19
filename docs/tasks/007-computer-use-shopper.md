# Task 007 — Run the five shopper stories with a computer-use agent

**Status** · Closed on 2026-11-19. The live shopper passed all five stories on its first attempt per story.

Use the same generated storefront and grading criteria as the [scripted runner](006-scripted-browser-tests.md). The shopper receives the request and interacts with the site through browser screenshots, clicks, scrolling, and typing. The harness holds the expected answers and observes the mock checkout.

## Running and grading

Provide one local command that accepts the generated site directory, its source feed, and the shopper model. Reuse Task 6’s serving and grading code so both runners evaluate the same build. Record the build identity, model, and attempt limits with the results.

For a lookup, the shopper returns the requested facts as its final answer. Grade those facts using Task 6’s formatting rules and check for zero submissions. For checkout, check the mock’s accepted order and the confirmation visible in the browser. For the edit story, the first instruction ends with “Show me my cart.” When the shopper signals it is ready, verify one tea and one rice in the visible cart before releasing the second instruction.

## Pass@3 per story

1. Start each attempt on the homepage with an empty cart, a fresh agent conversation, and a separate record of mock order activity. Use the same build, shopper request, model settings, and step limit across attempts.
2. Grade the whole attempt against the [agreed story outcome](../website-feature-roadmap.md#agreed-thai-peacock-shopper-stories). For the edit story, give the change request only after the initial cart is verified. Both stages must succeed in the same attempt.
3. Stop trying that story as soon as it passes. After three unsuccessful attempts, mark it failed. Continue until all five stories have a result.
4. Report how many stories passed out of five and the result of each attempt taken. Keep the action history and screenshot for each failure, including failures followed by a successful retry.

The suite passes when all five stories pass within their individual three-attempt limits. A full run takes between five and fifteen attempts.

A wrong answer, wrong order, or exhausted shopper step budget uses an attempt. If the browser, model service, or mock is unavailable and grading cannot finish, stop the run and report it as incomplete. Keep completed results. Choose and document a default step limit during the first live run, then hold it fixed for comparisons.

## Done when

- A teammate can run all five stories against the Task 6 build and find the per-attempt results, failure reasons, and evidence. The command signals success only for a 5/5 pass.
- A repeatable test of the retry logic demonstrates a first-attempt pass, a pass on the second attempt, and three failures. Check that early stopping skips only the remaining attempts for that story and that a retry inherits no cart, conversation, or order events.
- Run the real computer-use shopper on the template-generated Thai Peacock site and record the baseline, including the model identifier, how many stories passed on their first attempt, and how many passed within three.

## Run locally

From the repository root, use the existing Task 006 build, the feed that generated it, and an OpenAI key in `.env`. If the key is already exported, omit `--env-file .env`. Task 006 installs the required Chromium browser. On a fresh checkout with a copied build, install it once with `make shopper-browser`.

```sh
uv run --locked --package webbuilder-shopper --env-file .env run-computer-shopper \
  --site build/thai-peacock --feed ~/data/webbuilder/restaurants_feed.json \
  --model gpt-5.4-2026-03-05
```

The runner copies the supplied site once and serves that snapshot for every attempt. It uses Task 006’s local storefront, mock checkout, cart and confirmation readers, and fact and order graders. The computer shopper opens the homepage directly. Its new browser context has empty cart storage. A new Chromium context and OpenAI conversation start each attempt. The model receives the shopper’s request, viewport screenshots and the computer tool. The grader reads the final text for lookups, the visible page for cart and receipt checks, and the mock’s complete record after outstanding checkouts finish.

The default budget is **32 model turns per attempt**, shared across the two requests in the edit story. One response counts as one turn, including a batch of actions or a final answer. Each story gets **up to three attempts**, ending at the first pass. To set a different budget for a separate comparison, pass `--step-limit N`.

The command prints every attempt and writes `report.json` under a fresh `logs/computer-shopper/<run>/` directory. Each row records the final answers, steps, grading reason, mock submissions, and the path to its action history. Every failed attempt also has a PNG of the final browser view. A verified edit checkpoint has a separate viewport PNG recorded in `checkpoint_screenshot` before the second request is released. That image stays with the attempt even if checkout fails. A service interruption stops the run and preserves completed attempts. Exit codes are `0` for five passing stories, `1` for a completed run with failures, and `2` for an incomplete run. To keep evidence elsewhere, pass a new or empty directory with `--evidence`.

## Live baseline · 2026-11-19

- **Build** · Task 006 template-generated `build/thai-peacock`, store `265151`. SHA-256 `fa7738a6d3846517f324576391d6187b8795a8355e490926d1ccc2442eefefd9`. The digest covers the sorted relative paths and content hashes of all eight files, including the existing `preview.png`. [Build manifest](evidence/007-baseline/build-files.json)
- **Source feed** · `~/data/webbuilder/restaurants_feed.json`, SHA-256 `45a4250e335a3197505941fcccd2a1cd9a63b54f0afc550301f53bd82c63c02d`.
- **Shopper** · OpenAI Responses `gpt-5.4-2026-03-05`, native `computer` tool, low reasoning effort, 2,048 maximum output tokens per response. Playwright 1.65.2, headless Chromium, 1280 × 900 PNG screenshots. The build, shopper instructions, model settings, and 32-turn budget were held fixed across attempts.
- **Evidence** · The baseline command used `--evidence docs/tasks/evidence/007-baseline`. The report links each attempt to its action history and any failure screenshot. [Baseline report](evidence/007-baseline/report.json)

**First attempt · 5/5. Within three attempts · 5/5.** The command exited with code 0 after five attempts.

| Story | Attempt | Turns | Graded result |
| --- | --- | ---: | --- |
| [Contact details](evidence/007-baseline/contact-1.json) | 1 · pass | 3 | Full address and phone number correct. Zero submissions. |
| [Posted hours](evidence/007-baseline/hours-1.json) | 1 · pass | 3 | Tuesday 11:30 AM–9:15 PM and Friday 11:00 AM–9:45 PM. Zero submissions. |
| [Menu lookup](evidence/007-baseline/soup-1.json) | 1 · pass | 5 | Tom-Yum Soup, 24 oz, $14.50. Zero submissions. |
| [Place an order](evidence/007-baseline/place-1.json) | 1 · pass | 14 | One accepted order and matching visible confirmation for two servings of spring rolls and one rice, $19.50. |
| [Change an order](evidence/007-baseline/change-1.json) | 1 · pass | 14 | The cart showed one tea and one rice before the second request. One accepted order and matching visible confirmation for two teas, $9.00. |

### Earlier incomplete run

The first run passed contact details (3 turns), hours (3), menu lookup (4), and place an order (13), each on attempt 1. On the edit story’s first attempt, the grader verified one tea and one rice at $7.00. The API returned HTTP 400 on turn 11 because the follow-up user message included another input image. The runner exited with code 2, recording four first-attempt passes and four within-three passes out of five, with the edit story incomplete and zero submissions for that attempt. The corrected follow-up sends the new instruction in the same conversation and continues to use screenshots from the computer tool. The baseline above starts a fresh five-story run. [Incomplete run report](evidence/007-incomplete/report.json) · [Edit action history](evidence/007-incomplete/change-1.json) · [Cart screenshot](evidence/007-incomplete/change-1.png)

## Repeatable verification

`make check` passed formatting, lint, strict type checks, and all **62 tests**. The retry test runs a deterministic shopper in real Chromium against the generated test storefront and its HTTP mock. It takes 1, 2, 3, 1, and 2 attempts across the five stories, retaining five failure screenshots and histories. A failed lookup leaves an accepted order and a new cart item behind. Its retry begins on the homepage with a clean cart, fresh conversation, and zero submissions. A failed edit checkpoint receives only the first request. Separate tests interrupt the browser, model, and mock after a completed story and verify the saved results. Task 006’s scripted runner also passed all five stories against the existing baseline build. [Retry and outage tests](../../tests/test_computer_runner.py) · [Computer tool and handoff tests](../../tests/test_computer_model.py)

## Grading changes after the baseline

The baseline above was collected with the original grader. Subsequent runs require the cart item names and quantities, and the graded confirmation fields, to intersect the shopper’s viewport. The grader observes the current scroll position and saves the verified cart view. The soup grader checks for conflicting menu item names and accepts concise answers such as “24 oz, $14.50” as referring to the dish in the request. In descriptive answers, naming Tom-Yum alongside its size and price makes that attribution explicit.

`make check` passed all 85 tests after the grading changes. The scripted runner also passed all five stories on a temporary copy of the baseline build with the empty-cart message changed to “Your basket is empty.” Regression tests exercise renamed empty-cart text, offscreen cart and receipt fields, facts attributed to a different soup, and a verified cart screenshot retained through a later checkout failure. [Viewport tests](../../tests/test_shopper_viewport.py) · [Lookup grading tests](../../tests/test_shopper_grading.py) · [Attempt and evidence tests](../../tests/test_computer_runner.py)
