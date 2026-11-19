# Task 002 — Generate and review the Thai Peacock storefront

**Status** · Closed on 2026-11-19 after owner review.

**Outcome** · Verified the landing page, all 13 menu sections and 18 entries, and the hours and location page directly in Chrome. Open `build/thai-peacock/index.html` for the reviewed storefront. [Regeneration command](../../README.md#preview-thai-peacock)

Build the first desktop storefront for Thai Peacock (`265151`). A reviewer should be able to open the generated HTML directly in a browser, browse the menu, and point out what to change.

## Deliverable

- Add a generator in `webbuilder-agent` that takes the feed path, store ID, and output directory. Document one command that reads `~/data/webbuilder/restaurants_feed.json` for store `265151` and writes an `index.html` with any local assets it uses.
- Use the selected store’s name, cuisine, and supplied imagery to give the page its identity. Show the address, phone number, and posted hours, preserving each day’s supplied intervals.
- Put the restaurant introduction and up to three tag-matched, photographed dishes on the landing page. Link each featured dish to its full menu entry. Both **Menu** and **Order now** open the menu page. Group the phone, address and posted hours on **Hours & location**.
- Provide section navigation and render every supplied section and item in feed order. Show names, listed prices, descriptions, and photos where available. Keep choice instructions in the menu copy. Retain the store ID, item IDs, currency, and prices in cents in the generated output for the browser cart in Task 004.

## Review and completion

1. Run the command and open `index.html` directly on desktop. Check that the page styling loads and section links work.
2. Verify all **13 sections and 18 entries** are present. Under **Small Plates**, find Vegan Crispy Spring Rolls (`140240246`, $8.50). Under **Sides**, find Rice (16oz.) (`140247117`, $2.50). Check that both placements of the Lychee Hibiscus Daiquiri survive with their distinct item IDs.
3. Review the rendered page with the owner. Make revisions in the generator or its templates, regenerate with the same command, and inspect the result. Close when the owner is happy with this example. Task 003 will serve this output.

[Feed profile and item examples](../restaurant-feed-profile.md) · [Tier 1 feature scope](../website-feature-roadmap.md)
