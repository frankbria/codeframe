from decimal import Decimal

from shop.cart import Cart

PER_ITEM = Decimal("5.00")
FREE_SHIPPING_OVER = Decimal("50.00")


def shipping_cost(cart: Cart) -> Decimal:
    """$5 per item; free when the subtotal is over $50."""
    cost = Decimal("0.00")
    for item in cart.items:
        if cart.subtotal <= FREE_SHIPPING_OVER:
            cost += PER_ITEM * item.qty
    return cost
