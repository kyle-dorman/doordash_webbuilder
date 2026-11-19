# Task 001 — Explore the restaurant feed and choose MVP test cases

**Status** · Closed on 2026-11-19 after owner review.

The MVP will generate a white-label site for each restaurant, show its full supplied menu, and send orders to a mocked DoorDash checkout. Start with a short report that gives the project owner enough evidence to discuss which restaurant to build against first and which data gaps matter for the demo.

**Input** · `~/data/webbuilder/restaurants_feed.json`

**Outcome** · The [feed profile](../restaurant-feed-profile.md) compares all 12 stores and proposes Thai Peacock for the first walkthrough, One Stop Roti for a storefront without photos, and Joy for a dish with unspecified sizes.

**Next task** · [Generate the Thai Peacock storefront](002-generate-static-storefront.md). The [feature roadmap](../website-feature-roadmap.md) lists the Tier 1 tasks in build order. Tier 1 displays the supplied choice wording. Size, protein, and side selectors are Tier 2 features.

## First pass

1. **Describe the feed.** Read the full file and record its `generated_at` value. Map the main objects in plain language. Follow one item from restaurant to menu list to item ID and price so a teammate can find it again.
2. **Compare the restaurants.** Make a compact table keyed by store ID and name. Show menu-list and item counts, item photo coverage, and the brand or style cues available for each restaurant. Count menu entries as supplied and check whether item IDs repeat across lists before interpreting those counts as distinct dishes.
3. **Identify differences that matter to the MVP.** Look for cases that change what a customer could see or order, such as empty lists, missing descriptions or imagery, repeated items, unusual prices, or choices and modifiers. Check what the feed actually provides for styling and constructing a mock order. For each material finding, give its frequency or a specific store and field path, describe the impact, and recommend handling it now or deferring it. A one-line reason is enough for a deferral.
4. **Propose candidate test cases.** Suggest one restaurant for the first end-to-end build and one or two others that exercise meaningfully different behavior. For each, give the exact store ID, the data that motivated the choice, and one observable expectation for the eventual site or checkout. Where an individual menu item makes the case, include its list and item ID.

## Review together

Share the initial report and pause for the owner's input. Open the discussion with a concrete question grounded in the findings. Keep the task open and the proposed test cases and deferrals provisional.

Use the owner's feedback to choose the next example to inspect or comparison to run. Revise the report in place, recording decisions as they are made. An edge case can be acknowledged and set aside in a sentence. Close the task when the owner agrees there is enough evidence to move on.

Keep this task to local, read-only feed exploration and the report. Fixture extraction, application changes, and automated tests can follow once the cases are chosen.
