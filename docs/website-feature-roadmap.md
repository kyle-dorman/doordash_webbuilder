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
| [006 · Scripted browser tests](tasks/006-scripted-browser-tests.md) | Generate and serve Thai Peacock, then run the five shopper stories below in a browser. |
| [007 · Computer-use shopper](tasks/007-computer-use-shopper.md) | Run the same five stories on the same generated site. Each story must pass within three attempts. |
| [008 · Agents SDK edit-story pilot](tasks/008-agents-sdk-edit-story.md) | Compare native and SDK runners on the two-request edit with GPT-5.4 held fixed. |
| [009 · Shopper model comparison](tasks/009-shopper-model-comparison.md) | Compare GPT-5.4 and GPT-6.1 Terra on all five stories using the verified SDK runner. |
| [010 · Split the shopper testers](tasks/010-split-shopper-testers.md) | Separate scripted Playwright checks from the SDK computer-use shopper and retire the native runner. |

### Agreed Thai Peacock shopper stories

Both runners start each story on the homepage with an empty cart. The three lookups require a correct answer from the site and zero order submissions. Each order requires exactly one accepted mock order for Thai Peacock (`265151`) and a matching confirmation visible to the shopper.

| Story | Shopper request | Expected outcome |
| --- | --- | --- |
| Contact details | What’s the full address and phone number? | 219 Southwest 9th Avenue, Portland, OR 97205 and (503) 719-7273. |
| Posted hours | When does Thai Peacock open and close on Tuesday and Friday? | Tuesday 11:30 AM–9:15 PM and Friday 11:00 AM–9:45 PM, local time. |
| Menu lookup | What size is the Tom-Yum Soup, and how much does it cost? | 24 oz and $14.50. |
| Place an order | Order two servings of vegan crispy spring rolls and one 16 oz rice. | Two spring rolls orders (`140240246`, $17.00 together) and one rice (`140247117`, $2.50), totaling **$19.50**. |
| Change an order | Add one Thai Lime Tea and one 16 oz rice to the cart. Once both appear, change to two teas, remove the rice, and place the order. | The cart initially shows one of each. The accepted order contains only two teas (`548484849`), totaling **$9.00**. |

## Tier 2 · Planned enhancements

- **Dish-detail popups.** Let a shopper open a dish from the menu, read its details, and add it to the cart from the popup. Extend the scripted runner to cover this path with the same order expectations.
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
