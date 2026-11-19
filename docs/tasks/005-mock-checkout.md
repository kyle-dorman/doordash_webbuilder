# Task 005 — Submit the order to the mock backend

**Status** · Planned after [Task 004 — Browser cart](004-browser-cart.md).

Connect the shared order review page to `webbuilder-mock-backend`. The customer should be able to place a simulated order and read its confirmation on the restaurant site.

## Order flow

1. When the customer selects **Place order**, send the store ID and a list of item IDs with their quantities. Cart edits stay in the browser until this action.
2. Look up each item in that store’s feed menu. Accept positive whole-number quantities and calculate line amounts and the subtotal from the listed prices in integer cents.
3. Return the confirmed items, quantities, and subtotal. Show them on a shared confirmation view and label the order as simulated. If the request fails, keep the cart available for correction or retry.

## Done when

- From the locally served Thai Peacock site (`265151`), order two crispy spring rolls (`140240246`, $8.50 each) and one rice (`140247117`, $2.50). The mock returns line amounts of $17.00 and $2.50, and the confirmation shows **$19.50**.
- An item belonging to another store or a quantity of zero yields an error. Only an accepted order shows a confirmation.
- As a final check, enter One Stop Roti’s ID (`26303866`) in the same generator. On its storefront without photos, order one Curry Chicken (`10703144790`) and confirm **$14.95** using the same cart and checkout.
- A teammate can run the site and mock locally and repeat the walkthrough using the project’s run instructions.
