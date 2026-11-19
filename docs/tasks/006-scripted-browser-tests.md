# Task 006 — Run the five shopper stories in Playwright

**Status** · Closed on 2026-11-19. All five stories passed in Playwright.

One local command generates Thai Peacock’s storefront, starts the site and mock checkout, and runs the [five agreed shopper stories](../website-feature-roadmap.md#agreed-thai-peacock-shopper-stories) against that build. Each story starts at the homepage in a fresh browser session.

## Browser interactions

Use the links, dish names, and labeled controls available to a shopper. To order Thai Lime Tea, for example, find the tea by name and activate its add button directly on the menu. Moving the dish to a different position or restyling its button should preserve the test.

## Done when

- Each lookup reads the requested facts from visible page content and compares them with the agreed answers. Equivalent phone, time, and price formatting passes. The mock receives zero submissions during each lookup.
- Each checkout produces exactly one accepted mock order with the expected store, items, quantities, and subtotal. The shopper sees a matching confirmation.
- The cart-edit story verifies one tea and one rice in the visible cart before changing the quantity and removing the rice.
- The command reports a result for each story. A checkout that displays a confirmation without an accepted mock order fails.

## Run locally

With the sample feed at `~/data/webbuilder/restaurants_feed.json`, run this from the repository root.

```sh
make stories
```

The command installs the locked Playwright browser on first use and generates `~/data/webbuilder/runs/reference/thai-peacock`. Each story opens that build’s homepage in a fresh Chromium session, checks the empty cart, and returns home to begin shopping. Each gets a separate local storefront and mock on automatically assigned ports. The servers finish pending submissions and shut down before the runner grades the mock record. A failed story prints its reason and the next story runs. The command exits successfully only on a five-story pass.

## Verification

Observed on the generated Thai Peacock site (store `265151`) with Playwright 1.65.2.

| Story | Visible result | Submissions received by the mock |
| --- | --- | --- |
| Contact details · **PASS** | 219 Southwest 9th Avenue, Portland, OR 97205 and (503) 719-7273 | 0 |
| Posted hours · **PASS** | Tuesday 11:30 AM–9:15 PM and Friday 11:00 AM–9:45 PM | 0 |
| Menu lookup · **PASS** | Tom-Yum Soup, 24 oz, $14.50 | 0 |
| Place an order · **PASS** | Confirmation showed two servings of vegan crispy spring rolls ($17.00) and one 16 oz rice ($2.50), totaling **$19.50** | 1 accepted · `140240246` × 2 and `140247117` × 1, 1,950 cents |
| Change an order · **PASS** | Cart showed one Thai Lime Tea and one 16 oz rice before the edit. Confirmation showed only two teas, totaling **$9.00** | 1 accepted · `548484849` × 2, 900 cents |

The runner reported **5/5 stories passed**. All five also passed with the menu order reversed, add buttons restyled, and equivalent phone, time, and price formatting.

In a temporary copy of the build, checkout displayed the same receipts without sending the orders. Both checkout stories failed on zero mock submissions and all three lookups passed. A separate run with a malformed cart quantity stopped the edit story at its checkpoint, before submission.

`make check` passed formatting, lint, strict type checks, and all 36 tests.

## Reuse for Task 007

The serving helper accepts an existing site directory and the catalog loaded from its source feed. It gives each attempt a homepage URL and a record of every submission received by its mock, including rejections. The graders accept lookup strings, visible cart or receipt lines, and the mock record. The cart and confirmation readers can observe the browser at the computer-use shopper’s checkpoints. [Serving](../../packages/shopper/src/webbuilder_shopper/serving.py) · [Grading](../../packages/shopper/src/webbuilder_shopper/grading.py) · [Browser readers](../../packages/shopper/src/webbuilder_shopper/viewport.py)
