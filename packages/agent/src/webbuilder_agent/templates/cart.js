(() => {
  const catalog = JSON.parse(document.getElementById("cart-catalog").textContent);
  const items = new Map(catalog.items.map(item => [item.item_id, item]));
  const storageKey = `webbuilder:cart:${catalog.store_id}`;
  const counts = document.querySelectorAll("[data-cart-count]");
  const status = document.querySelector("[data-cart-status]");
  const lines = document.querySelector("[data-cart-lines]");
  const template = document.getElementById("cart-line-template");
  const empty = document.querySelector("[data-cart-empty]");
  const subtotal = document.querySelector("[data-cart-subtotal]");

  function loadCart() {
    const cart = new Map();
    try {
      const saved = JSON.parse(sessionStorage.getItem(storageKey) ?? "[]");
      if (Array.isArray(saved)) {
        for (const line of saved) {
          if (items.has(line?.item_id) && Number.isSafeInteger(line.quantity) && line.quantity > 0) {
            cart.set(line.item_id, line.quantity);
          }
        }
      }
    } catch {
      // An unreadable cart can be replaced on the next successful edit.
    }
    return cart;
  }

  let cart = loadCart();

  function money(cents, currency) {
    return (cents / 100).toLocaleString("en-US", {style: "currency", currency});
  }

  function createLine(item) {
    const line = template.content.firstElementChild.cloneNode(true);
    line.dataset.itemId = item.item_id;
    line.querySelector("[data-cart-name]").textContent = item.name;
    line.querySelector("[data-cart-unit-price]").textContent = `${money(item.price_cents, item.currency)} each`;
    for (const [action, label] of [
      ["decrease", "Decrease quantity of"], ["increase", "Increase quantity of"], ["remove", "Remove"],
    ]) {
      line.querySelector(`[data-cart-action="${action}"]`).setAttribute("aria-label", `${label} ${item.name}`);
    }
    return line;
  }

  function render() {
    const count = Array.from(cart.values()).reduce((total, quantity) => total + quantity, 0);
    for (const counter of counts) counter.textContent = count;
    if (!lines) return;

    // Keep existing controls in the DOM so changing a quantity preserves keyboard focus.
    const oldLines = new Map(Array.from(lines.children, line => [line.dataset.itemId, line]));
    let subtotalCents = 0;
    for (const [id, quantity] of cart) {
      const item = items.get(id);
      const line = oldLines.get(id) ?? createLine(item);
      const lineCents = item.price_cents * quantity;
      line.querySelector("[data-cart-quantity]").textContent = quantity;
      line.querySelector("[data-cart-line-total]").textContent = money(lineCents, item.currency);
      if (!line.parentElement) lines.append(line);
      oldLines.delete(id);
      subtotalCents += lineCents;
    }
    for (const line of oldLines.values()) line.remove();
    empty.hidden = cart.size > 0;
    subtotal.textContent = money(subtotalCents, catalog.items[0]?.currency ?? "USD");
  }

  function setQuantity(id, quantity) {
    if (!Number.isSafeInteger(quantity) || quantity < 0) return;
    const next = new Map(cart);
    if (quantity === 0) next.delete(id);
    else next.set(id, quantity);

    try {
      const saved = Array.from(next, ([item_id, quantity]) => ({item_id, quantity}));
      sessionStorage.setItem(storageKey, JSON.stringify(saved));
    } catch {
      status.className = "cart-notice";
      status.textContent = "Your browser couldn’t save the cart. Allow site storage and try again.";
      return;
    }
    cart = next;
    render();
    status.className = "visually-hidden";
    const name = items.get(id).name;
    status.textContent = quantity ? `${name}, quantity ${quantity}.` : `${name} removed.`;
  }

  document.addEventListener("click", event => {
    const add = event.target.closest("[data-add-item]");
    if (add && items.has(add.dataset.addItem)) {
      const id = add.dataset.addItem;
      setQuantity(id, (cart.get(id) ?? 0) + 1);
      return;
    }

    const control = event.target.closest("[data-cart-action]");
    if (!control || !lines?.contains(control)) return;
    const line = control.closest("[data-item-id]");
    const id = line.dataset.itemId;
    const action = control.dataset.cartAction;
    const quantity = cart.get(id);
    if (action === "increase") setQuantity(id, quantity + 1);
    if (action === "decrease") setQuantity(id, quantity - 1);
    if (action === "remove") setQuantity(id, 0);
    if (!cart.has(id)) {
      const next = lines.querySelector("[data-cart-action]") ?? empty;
      if (next === empty) empty.tabIndex = -1;
      next.focus();
    }
  });

  render();
  window.addEventListener("pageshow", event => {
    if (event.persisted) {
      cart = loadCart();
      render();
    }
  });
})();
