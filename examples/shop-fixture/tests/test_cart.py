from decimal import Decimal

from shop.cart import Cart


def test_cart_subtotal():
    cart = Cart()
    cart.add("mug", "12.50", qty=2)
    cart.add("tea", "4.25")
    assert cart.subtotal == Decimal("29.25")
