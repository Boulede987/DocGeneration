"""UML relations between classifiers, as the PlantUML arrows that draw
them. Which relations exist is decided by each language."""

from dataclasses import dataclass
from enum import Enum, IntEnum

INHERITS = "--|>"
REALIZES = "..|>"
COMPOSES = "*-->"
AGGREGATES = "o-->"
ASSOCIATES = "-->"
DEPENDS = "..>"
MANY = '"0..*"'


class RelationLevel(IntEnum):
    """Strength order: INHERITANCE < STRONG < WEAK. Base views show up to
    STRONG, full views everything."""
    INHERITANCE = 0
    STRONG = 1
    WEAK = 2


class PackageLookup(Enum):
    """The target's package is found from its name, through the file's
    imports and the project's declarations."""
    BY_NAME = "by name"


@dataclass(frozen=True)
class Relation:
    """Ends are bare simple names, never package-qualified. A language that
    knows exactly where the target is declared gives target_package (None:
    no package), so a target named like a declaration of the file itself
    still lands in its own package."""
    source: str
    arrow: str
    target: str
    level: RelationLevel
    multiplicity: str | None = None
    target_package: str | None | PackageLookup = PackageLookup.BY_NAME

    def render(self, qualified_source: str, qualified_target: str) -> str:
        """The PlantUML line, with the ends as the caller qualified them."""
        multiplicity = f" {self.multiplicity}" if self.multiplicity else ""
        return f"{qualified_source} {self.arrow}{multiplicity} {qualified_target}"
