"""The contract a language implements to plug into the shared pipeline."""

from abc import ABC, abstractmethod
from typing import Generic, Mapping

from .model import FactsT, ParsedFile, SourceText
from .project import Project
from .relations import Relation


class Language(ABC, Generic[FactsT]):
    """Class attributes every language sets:
    name            registry key, e.g. "java"
    source_suffix   e.g. ".java"
    views_dir       folder for package-level views, e.g. "Packages"
    skinparam_lines PlantUML styling put at the top of every diagram

    FactsT is what the language keeps from parsing (ParsedFile.facts) to
    compute relations once the whole project is parsed.
    """
    name: str
    source_suffix: str
    views_dir: str
    skinparam_lines: list[str]

    @abstractmethod
    def parse_file(self, source: SourceText) -> ParsedFile[FactsT]:
        """Parse one source file into UML declarations. Return a ParsedFile
        with no declarations when the file declares no type; raise when the
        text can't be parsed (only that file fails)."""

    @abstractmethod
    def link(self, project: Project[FactsT]) -> Mapping[ParsedFile[FactsT], list[Relation]]:
        """Once every file is parsed: each file's relations (ends are bare
        names); a file absent from the result has none. May also complete
        declarations across files (e.g. methods declared away from their
        type) and add notes to files. Raising leaves every diagram without
        relations and fails the run."""

    def enclosing_packages(self, package: str | None) -> list[str | None]:
        """Packages whose types this package sees without an import,
        closest first."""
        return [package]
