# Task 001 — Explore the restaurant feed and choose MVP test cases

**Status** · Ready to start

The MVP will generate a white-label site for each restaurant, show its full supplied menu, and send orders to a mocked DoorDash checkout. Use this task to decide which restaurant to build against first, which others to test next, and which data gaps we can live with for the demo.

**Input** · `~/data/webbuilder/restaurants_feed.json`

**Deliverable** · A short findings report at `docs/restaurant-feed-profile.md`

## Investigate

1. **Describe the feed.** Read the full file and record its `generated_at` value. Map the main objects in plain language. Follow one item from restaurant to menu list to item ID and price so a teammate can find it again.
2. **Compare the restaurants.** Make a compact table keyed by store ID and name. Show menu-list and item counts, item photo coverage, and the brand or style cues available for each restaurant. Count menu entries as supplied and check whether item IDs repeat across lists before interpreting those counts as distinct dishes.
3. **Identify differences that matter to the MVP.** Look for cases that change what a customer could see or order, such as empty lists, missing descriptions or imagery, repeated items, unusual prices, or choices and modifiers. Check what the feed actually provides for styling and constructing a mock order. For each material finding, give its frequency or a specific store and field path, describe the impact, and recommend handling it now or deferring it. A one-line reason is enough for a deferral.
4. **Pick the first test cases.** Recommend one restaurant for the first end-to-end build and one or two others that exercise meaningfully different behavior. For each, give the exact store ID, the data that motivated the choice, and one observable expectation for the eventual site or checkout. Where an individual menu item makes the case, include its list and item ID.

## Done when

Someone reading the report can locate each recommended case in the feed, explain what it tests, and tell which limitations the team is accepting for the first demo. Keep the work to local, read-only exploration and the findings report. Fixture extraction, application changes, and automated tests can follow once the cases are chosen.
