from typing import Generic, TypeVar

T = TypeVar("T")


class Box(Generic[T]):
    def __init__(self, item: T):
        self.item = item

    def get(self) -> T:
        return self.item


class Validator:
    @staticmethod
    def check(value: object) -> bool:
        return value is not None
