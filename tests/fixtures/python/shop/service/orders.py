from __future__ import annotations

from typing import Optional, Protocol

from shop.model.product import Money, Product
from vendor.payments import PaymentGateway

from ..model import base
from ..util.helpers import Validator


class Repository(Protocol):
    def find(self, key: str) -> Optional[Product]:
        ...

    def save(self, product: Product) -> None:
        ...


class Auditable:
    def audit(self) -> list[str]:
        return []


class BaseService:
    name = "service"


class OrderService(BaseService, Auditable):
    def __init__(self, repository: Repository):
        self.repository = repository
        self.__orders: dict[str, Order] = {}
        self.gateway = PaymentGateway()
        self.history = []

    @staticmethod
    def total(items: list[Product]) -> Money:
        amount = Money(0)
        for item in items:
            amount = amount.plus(item.price)
        return amount

    @classmethod
    def create(cls, repository: Repository) -> OrderService:
        return cls(repository)

    def _check(self, product: Product) -> bool:
        return Validator.check(product)


class Order(base.Entity):
    def __init__(self, id: int, product: Product):
        super().__init__(id)
        self.product = product

    def validate(self) -> None:
        pass
