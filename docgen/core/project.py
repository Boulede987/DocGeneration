"""Everything parsed in one run, as a language sees it when computing
relations."""

from dataclasses import dataclass, field
from typing import Generic

from .model import FactsT, ParsedFile
from .resolution import ProjectIndex


@dataclass
class Project(Generic[FactsT]):
    files: list[ParsedFile[FactsT]]
    # Built from the files as parsed: a language merging declarations
    # across files in link() adds members, never new types.
    index: ProjectIndex = field(init=False)

    def __post_init__(self) -> None:
        self.index = ProjectIndex(self.files)
