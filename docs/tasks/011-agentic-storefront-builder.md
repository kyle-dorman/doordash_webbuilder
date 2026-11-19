# Task 011 — Build restaurant storefronts with an Inspect AI agent

**Status** · Closed on November 19, 2026. [Task 010](010-split-shopper-testers.md#verification) is closed.

Give the builder one restaurant’s feed and a desktop storefront brief. Let it decide how a diner first encounters the restaurant, browses the full menu, and starts an order. Keep the existing generator available for side-by-side review. The pilot should answer two questions. Do the designs suit the individual restaurants? Did seeing the first render help the agent improve it?

## Implementation plan

1. **Rename the reference generator in its own change.** Move the current package to `packages/static` (`webbuilder-static`, imported as `webbuilder_static`). Keep `generate-storefront --feed … --store-id … --output …`. Before and after the rename, generate Thai Peacock and One Stop Roti from the same feed into fresh directories and compare emitted paths and file hashes. Update workspace dependencies, template loading, callers, tests, and current README commands. Verify that `make stories` still runs the reference without an API key.
2. **Share the pieces that make an order work.** Give both builders the feed reader, item catalog, add-to-cart button bound to an item ID, cart JavaScript, and cart review and receipt markup. Include quantity changes, status messages, checkout errors, and the existing same-origin `POST /orders` flow. Load that support on any page where a diner can add an item. Supply restaurant identity and navigation targets explicitly so checkout works with a custom header and a menu on the homepage.
3. **Give the agent ownership of the storefront.** Create a new `packages/agent` (`webbuilder-agent`, imported as `webbuilder_agent`). Add a separate command, proposed as `generate-agent-storefront`, with the same three build arguments and a configurable vision-capable Inspect model. Start with an empty design workspace and the shared components. The agent writes page templates and CSS, including navigation, menu-item layout, and the placement of hours and contact details. It can style the shared controls. Render restaurant facts and all menu entries from the feed, preserving section order, repeated listings, prices, and supplied imagery. Use the same brief for both stores and let the feed supply the design cues.
4. **Run one bounded build per restaurant.** Use Inspect’s `react()` with two project tools. One edits the build’s templates and CSS. The other renders the current draft, serves it locally, and returns the requested page as a Playwright screenshot at the shopper’s 1280 × 900 viewport. Return render errors to the agent so it can fix them. The agent previews a successful render, then submits it or edits and previews again within a configurable message budget. Save the first successful build and the submitted build with comparable screenshots, the model and budget, and the Inspect log. A run that exhausts its budget before submission is incomplete. [Inspect ReAct agent](https://inspect.aisi.org.uk/react-agent.html)

## Verification and review

- **Reference and build loop.** Run `make check` and all five scripted reference stories. Exercise an edit → preview → revision → preview → submit sequence offline with a model fixture and real Chromium. Check that the model receives the screenshot, the saved first render survives revision, and the final output matches the submitted preview.
- **Thai Peacock, store `265151`.** After the agent submits, point `run-computer-shopper --site … --feed …` at that exact output. All five stories should pass under Task 010’s existing attempt rules, including the $19.50 order and the cart edit ending at $9.00. Record the report and any failed attempts. The shopper runs independently after submission. Giving its feedback to the builder is a later experiment. [Shopper stories](../website-feature-roadmap.md#agreed-thai-peacock-shopper-stories)
- **One Stop Roti, store `26303866`.** Run the same builder on this text-only store. Walk through ordering one Curry Chicken from the Roti section. Verify one accepted mock order for item `10703144790` and a matching visible $14.95 receipt. Across both builds, check the full menu against the feed, including both Thai Peacock daiquiri listings with their distinct IDs. [Feed profile](../restaurant-feed-profile.md)
- **Design review.** For each restaurant, open the static reference, first agent render, and submitted site side by side. Record one visible design choice tied to that restaurant’s feed and what changed after preview, if anything. Judge whether the design helps a diner browse and order. Report that judgment alongside the functional results so we can decide what to give the builder next.

## Pilot results

Both restaurants received the same brief and the normalized feed for their store. Each completed one Inspect ReAct run using `openai/gpt-5.4` and a 40-message limit. Thai Peacock submitted after four successful previews. One Stop Roti submitted after two. The first and final sites for each restaurant regenerated byte-for-byte from the saved templates. [Side-by-side comparison](evidence/011/index.html)

| Restaurant | Reference | First render | Submitted build | Inspect evidence |
| --- | --- | --- | --- | --- |
| Thai Peacock | [Browse](evidence/011/thai-peacock/reference/index.html) | [Browse](evidence/011/thai-peacock/agent/first/index.html) | [Browse](evidence/011/thai-peacock/submitted/index.html) | [Run record](evidence/011/thai-peacock/agent/run.json) · [Inspect log](evidence/011/thai-peacock/agent/logs/2026-11-19T22-58-35-00-00_build-storefront_AxrCYorqWg77cFQ3eEVnx4.eval) |
| One Stop Roti | [Browse](evidence/011/one-stop-roti/reference/index.html) | [Browse](evidence/011/one-stop-roti/agent/first/index.html) | [Browse](evidence/011/one-stop-roti/submitted/index.html) | [Run record](evidence/011/one-stop-roti/agent/run.json) · [Inspect log](evidence/011/one-stop-roti/agent/logs/2026-11-19T22-58-35-00-00_build-storefront_mvLCtgHR6xQdG7fAhprjwZ.eval) |

**Thai Peacock.** The supplied dining-table photograph sits beside the ordering link, phone and street address. A separate menu uses dish photographs and a 13-section index. After preview the agent widened the menu’s add-button column from 120 to 132 pixels and added space between button labels and cart counts. The index helps diners jump directly to a section. Its secondary checkout link still has low contrast against the rust-colored background. [First menu](evidence/011/thai-peacock/agent/previews/02-menu.png) · [Revised menu](evidence/011/thai-peacock/agent/previews/03-menu.png)

**One Stop Roti.** With no feed imagery, the homepage names roti, doubles and rice plates, offers shortcuts to menu sections and places the full menu on the same page. The first preview exposed dark lettering on an orange background. The agent changed “View order” to “Review order,” lightened its lettering and outline, and aligned the menu’s “Review cart” link with its heading. The revised control is easier to see. Individual dishes still begin below the opening viewport. [First homepage](evidence/011/one-stop-roti/agent/first.png) · [Submitted homepage](evidence/011/one-stop-roti/agent/final.png)

### Independent verification

The Task 010 computer-use shopper (`gpt-6.1-terra`) ran on the exact submitted Thai Peacock build. All five stories passed on the first attempt with the existing three-attempt, 32-turn limits. [Shopper report and build hash](evidence/011/shopper/report.json)

| Story | Turns | Observed result |
| --- | ---: | --- |
| Contact | 1 | Correct street address and phone, zero submissions |
| Hours | 4 | Tuesday 11:30 AM–9:15 PM and Friday 11:00 AM–9:45 PM, zero submissions |
| Menu lookup | 4 | Tom-Yum Soup, 24 oz., $14.50, zero submissions |
| Place order | 13 | Two orders of spring rolls and one rice, one accepted order, [$19.50 receipt](evidence/011/shopper/place-1.png) |
| Change order | 10 | [One tea and one rice](evidence/011/shopper/change-1-cart.png) before submission, then two teas, one accepted order, [$9.00 receipt](evidence/011/shopper/change-1.png) |

The independent menu check matched every supplied section, item ID, name, price, description and dish image URL in order, including both daiquiris (`913650617` and `478625263`). Thai Peacock had 18 items in 13 sections. One Stop Roti had 18 items in eight sections. Selecting Curry Chicken from Roti produced exactly one accepted order for item `10703144790`, quantity one, at 1,495 cents. The visible line total and grand total were both $14.95. [Menu and mock-order report](evidence/011/verification/report.json) · [Curry Chicken receipt](evidence/011/verification/roti-receipt.png)

The standalone rename commit `c6329c9` preserved the paths and bytes of all seven reference files per store. Both reference sites still matched after the shared checkout extraction. `env -u OPENAI_API_KEY make stories` passed all five scripted reference stories. `make check` passed formatting, lint, strict type checking and 100 tests. The Chromium-backed Inspect fixture covered render-error recovery, delivery of actual screenshots to the model, stale-preview rejection, revision and submission, and budget exhaustion. [Reference file hashes](evidence/011/rename.json) · [Offline fixture](../../tests/test_agent_builder.py)

To browse these saved sites with checkout, run the mock against the sample feed and serve the comparison directory from the repository root.

```sh
uv run --locked --package webbuilder-site-server serve-storefront \
  --directory docs/tasks/evidence/011 --port 8011 --mock-port 8001
```

Recheck the saved menus and One Stop Roti order against that same feed with a fresh evidence directory.

```sh
uv run --locked --all-packages python scripts/verify_agent_pilot.py \
  --feed ~/data/webbuilder/restaurants_feed.json \
  --thai-site docs/tasks/evidence/011/thai-peacock/submitted \
  --roti-site docs/tasks/evidence/011/one-stop-roti/submitted \
  --evidence logs/pilot-recheck
```
