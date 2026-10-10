from abc import ABC, abstractmethod


class Entity(ABC):
    """Identity shared by every stored object."""

    def __init__(self, id: int):
        self.id = id
        self._version = 0

    @abstractmethod
    def validate(self) -> None:
        ...

    @property
    def key(self) -> str:
        return f"{type(self).__name__}:{self.id}"
