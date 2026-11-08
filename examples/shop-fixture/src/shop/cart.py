from dataclasses import dataclass, field
from decimal import Decimal


@dataclass(frozen=True)
class LineItem:
    sku: str
    price: Decimal
    qty: int = 1


@dataclass
class Cart:
    items: list[LineItem] = field(default_factory=list)

    def add(self, sku: str, price: str, qty: int = 1) -> None:
        self.items.append(LineItem(sku, Decimal(price), qty))

    @property
    def subtotal(self) -> Decimal:
        return sum((item.price * item.qty for item in self.items), Decimal("0.00"))
