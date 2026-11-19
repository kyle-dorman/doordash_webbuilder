# Restaurant website feature roadmap

## Tier 1 · Desktop web MVP

The first build should let a customer find a dish, see what it costs, and complete a mocked DoorDash order on the restaurant’s site.

| Feature | Customer experience |
| --- | --- |
| Restaurant storefront | Recognize the restaurant by its name, cuisine, and supplied imagery. When photos are missing, the name and menu carry the page. |
| Full menu | Jump to a section and browse every supplied entry in feed order. Show names, prices, photos and descriptions where available. Preserve bilingual labels, repeated listings, and any choice instructions in the menu text. |
| Restaurant details | Find the address, phone number, and posted hours, including days with multiple opening intervals. |
| Cart | Add a menu item, change its quantity, or remove it. See the subtotal update at the listed prices, including explicitly free items such as utensils. |
| Mock checkout | Review the items, quantities, and subtotal, then place a simulated order and see its confirmation on the site. |

**Proposed first walkthrough.** At Thai Peacock (`265151`), add two orders of crispy spring rolls (`140240246`, $8.50 each) and one rice (`140247117`, $2.50). The cart and confirmation should both show $19.50. Then try One Stop Roti (`26303866`), where a customer should be able to find and order Curry Chicken even though the store has no images. [Restaurant feed profile](restaurant-feed-profile.md)

### Tier 1 tasks in build order

| Task | Milestone |
| --- | --- |
| [002 · Generate the static storefront](tasks/002-generate-static-storefront.md) | Open Thai Peacock’s HTML directly and iterate on the design together. |
| [003 · Serve the static storefront](tasks/003-serve-static-storefront.md) | Open the reviewed site at a local web address. |
| [004 · Browser cart and order review](tasks/004-browser-cart.md) | Build and edit an order in the browser and review its subtotal. |
| [005 · Mock checkout](tasks/005-mock-checkout.md) | Submit the order, verify the confirmation, and repeat with the text-only store. |

## Tier 2 · Planned enhancements

- **Size, protein, and side selection.** Let a customer choose an option, see what it costs, and review the selection in the cart and confirmation. Different sizes of the same item should stay on separate cart lines.
- **Menu search.** Find dishes across sections by name or description.
- **Ratings and reviews.** Show the aggregate rating and review count, with written reviews when supplied.
- **More control over styling.** Support restaurant-specific colors, typography, layouts, and logo overrides.

**Plan for item choices.** Start with one dish and confirm the option IDs, labels, prices, and whether a selection is required. Trace that choice from the menu through confirmation. The feed supplies choice wording only. For example, Joy’s Cold Salad Appetizers (`476002`, item `9287260604`) asks the customer to pick a size and lists $0.00. Its sizes and their prices are unknown. Tier 1 shows the supplied wording. Whether that particular item can enter the cart remains open.

## Tier 3 · Future backlog

These features are outside the current build.

- Mobile layouts and keyboard usability.
- Build-your-own meals and combos with multiple toppings, extras, or dependent choices.
- Item availability and scheduled orders.
- Pickup and delivery flows with fulfillment details and simulated fees and taxes.
- Order tracking and reordering a previous cart.
- Update shared storefront features across published restaurant sites without republishing each site.
