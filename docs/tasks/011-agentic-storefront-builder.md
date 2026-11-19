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

The saved run is in `~/data/webbuilder/runs/011/`. Open its `index.html` for the side-by-side comparison. Each restaurant directory contains `reference/`, `agent/first/`, `submitted/` and its Inspect log under `agent/logs/`.

Both builds used `openai/gpt-5.4` with the same feed-only brief and a 40-message limit. Thai Peacock submitted after four successful previews, widening the add-button column and separating cart counts from labels. One Stop Roti submitted after two previews, improving the contrast and wording of its review-order link. All four first and submitted builds regenerated byte-for-byte from their saved templates.

| Restaurant directory | Submitted build SHA-256 | Recorded result |
| --- | --- | --- |
| `thai-peacock/` | `5563418f164b2dde1035f31efcead57483636217f7c35e912d3d404f12f785b8` | All five shopper stories passed on the first attempt, including receipts of $19.50 and $9.00. All 18 menu entries in 13 sections matched, including both daiquiri IDs. |
| `one-stop-roti/` | `61dd04edcd718b54913cbc54385ee8d5620f0245a200d704a68f282e1229c9b8` | All 18 entries in eight sections matched. One Curry Chicken (item `10703144790`) produced one accepted order and a visible $14.95 receipt. |

The source feed SHA-256 was `45a4250e335a3197505941fcccd2a1cd9a63b54f0afc550301f53bd82c63c02d`. The archive contains the shopper attempts in `shopper/report.json`, menu and receipt checks in `verification/report.json`, and per-file reference hashes in `rename.json`. The original verification recorded byte-for-byte parity across all 14 reference files, five passing scripted reference stories without an API key, and 100 passing tests.

With the mock checkout running on port 8001, serve the saved comparison from the repository root and open [the local comparison](http://127.0.0.1:8011/).

```sh
uv run --locked --package webbuilder-site-server serve-storefront \
  --directory ~/data/webbuilder/runs/011 --port 8011 --mock-port 8001
```

### Independent Terra pilot

The [local comparison](http://127.0.0.1:8013/) is saved at `~/data/webbuilder/runs/agent/independent-20261119T233104Z/index.html`. Both restaurants used Terra with high reasoning effort and the same brief, with only their own feed as input. The earlier pair shared a split promotional opening. The revised brief gives the designer permission to skip that opening and start at a real ordering decision.

Thai Peacock opens with a comparison of its two 24 oz. soups. One Stop Roti opens directly on its curry-gold menu and lets diners follow an ingredient across sections. Both complete menus retained all 18 listings with JavaScript off. All five Thai stories passed on the first attempt, and the Roti checkout confirmed one Curry Chicken at $14.95. The submitted pair and its verification reports are in `second-pass/`. Roti’s first attempt there used its 60-message allowance before submission. Its retry used a 100-message allowance.
