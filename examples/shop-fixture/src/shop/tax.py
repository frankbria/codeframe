from decimal import ROUND_HALF_UP, Decimal

from shop.cart import Cart

TAX_RATE = Decimal("0.0825")


def tax(cart: Cart) -> Decimal:
    """Flat-rate tax on the subtotal, rounded half-up to the cent."""
    return (cart.subtotal * TAX_RATE).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
