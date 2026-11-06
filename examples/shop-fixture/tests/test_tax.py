from decimal import Decimal

from shop.cart import Cart
from shop.tax import tax


def test_tax_rounding():
    cart = Cart()
    cart.add("tea", "2.00")
    # 2.00 x 8.25% = 0.165: half-up gives 0.17 where banker's rounding gives 0.16.
    assert tax(cart) == Decimal("0.17")
