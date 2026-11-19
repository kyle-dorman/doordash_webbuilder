# Task 006 — Run the five shopper stories in Playwright

**Status** · Planned.

One local command generates Thai Peacock’s storefront, starts the site and mock checkout, and runs the [five agreed shopper stories](../website-feature-roadmap.md#agreed-thai-peacock-shopper-stories) against that build. Each story starts at the homepage in a fresh browser session.

## Browser interactions

Use the links, dish names, and labeled controls available to a shopper. To order Thai Lime Tea, for example, find the tea by name and activate its add button directly on the menu. Moving the dish to a different position or restyling its button should preserve the test.

## Done when

- Each lookup reads the requested facts from visible page content and compares them with the agreed answers. Equivalent phone, time, and price formatting passes. The mock receives zero submissions during each lookup.
- Each checkout produces exactly one accepted mock order with the expected store, items, quantities, and subtotal. The shopper sees a matching confirmation.
- The cart-edit story verifies one tea and one rice in the visible cart before changing the quantity and removing the rice.
- The command reports a result for each story. A checkout that displays a confirmation without an accepted mock order fails.
