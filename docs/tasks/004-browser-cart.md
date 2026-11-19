# Task 004 — Add a browser cart and order review

**Status** · Closed on 2026-11-19 after verification in Chrome.

Let a customer add items from the served menu and review a single restaurant’s order. Use the same cart and review UI for each restaurant. Read the store ID, item IDs, names, and prices from the generated storefront.

## Cart behavior

- Add an item from its menu entry. Adding the same item ID again increases its quantity.
- Let the customer adjust quantities, remove a line, and return to the menu with their selections intact. Show an empty-cart message when the last line is removed.
- Show each item’s name, unit price, quantity, and line total on review. Calculate the subtotal in integer cents and format it for display. Preserve listed zero-dollar prices.
- Keep cart edits and review in the browser. Carry the store ID and the item IDs with their quantities through to review. [Task 005](005-mock-checkout.md) will submit those selections when the customer places the order.

## Done when

Use Thai Peacock’s served site (store `265151`) for the walkthrough.

1. Add two orders of crispy spring rolls (`140240246`, $8.50 each) and one rice (`140247117`, $2.50). Review shows two lines and a **$19.50** subtotal.
2. Change the spring rolls to one order. The subtotal becomes **$11.00**. Remove the rice and the subtotal becomes **$8.50**.
3. Return to the menu and reopen review. The spring rolls are still there. Remove them and verify that the cart is empty and the subtotal is **$0.00**.

## Verification

- The served Thai Peacock storefront passed all three steps. Reloading the review page preserved the order. The two Lychee Hibiscus Daiquiri listings also retained independent quantities.
- One Stop Roti’s photo-free menu produced a **$14.95** subtotal for Curry Chicken. On the same local origin, Quang’s utensil pack stayed in its own cart and showed **$0.00** with a quantity of two.
- The generator test checks that two stores receive the same cart script and their own item data, including zero prices and distinct IDs for identically named dishes.
