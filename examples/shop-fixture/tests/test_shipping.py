from decimal import Decimal

from shop.cart import Cart
from shop.shipping import shipping_cost


def test_shipping_is_charged_per_item():
    cart = Cart()
    cart.add("mug", "12.50", qty=2)
    cart.add("tea", "4.25")
    assert shipping_cost(cart) == Decimal("15.00")


def test_empty_cart_ships_free():
    assert shipping_cost(Cart()) == Decimal("0.00")


def test_free_shipping_over_50():
    cart = Cart()
    cart.add("kettle", "45.00")
    cart.add("tea", "6.00")
    assert shipping_cost(cart) == Decimal("0.00")
