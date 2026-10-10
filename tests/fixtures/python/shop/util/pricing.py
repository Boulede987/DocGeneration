"""Pricing helpers: a functions-and-constants module, with no class."""

from shop.model.product import Money, Product, Tag

__all__ = ["total_price", "CURRENCY"]

CURRENCY = "EUR"
DEFAULT_TAG = Tag("new")
_cache: dict[str, Money] = {}


def total_price(products: list[Product]) -> Money:
    total = Money(0, CURRENCY)
    for product in products:
        total = total.plus(product.price)
    return _rounded(total)


def _rounded(amount: Money) -> Money:
    return Money(round(amount.cents, -1), amount.currency)
