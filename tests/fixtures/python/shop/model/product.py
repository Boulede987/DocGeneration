from dataclasses import dataclass, field
from enum import Enum, auto

from .base import Entity


class Category(Enum):
    BOOKS = "books"
    GAMES = auto()
    MUSIC = auto()


@dataclass
class Money:
    cents: int
    currency: str = "EUR"

    def plus(self, other: "Money") -> "Money":
        return Money(self.cents + other.cents, self.currency)


class Tag:
    label: str
    MAX_LENGTH = 32

    def __init__(self, label: str):
        self.label = label


@dataclass
class Product(Entity):
    name: str
    price: Money
    tags: list["Tag"] = field(default_factory=list)
    category: Category | None = None

    def validate(self) -> None:
        if not self.name:
            raise ValueError("a product needs a name")
