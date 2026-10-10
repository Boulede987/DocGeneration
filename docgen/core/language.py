"""The contract a language implements to plug into the shared pipeline."""

from abc import ABC, abstractmethod

from .model import ParsedFile, TypeDecl, TypeKind
from .relations import RelationPolicy
from .vocabulary import TypeVocabulary

ABSTRACT_STEREOTYPE = "<<abstract>>"
STATIC_STEREOTYPE = "<<static>>"
_KIND_STEREOTYPES = {
    TypeKind.RECORD: "<<record>>",
    TypeKind.STRUCT: "<<struct>>",
}


class Language(ABC):
    """Class attributes every language sets:
    name            registry key, e.g. "java"
    source_suffix   e.g. ".java"
    views_dir       folder for package-level views, e.g. "Packages"
    skinparam_lines PlantUML styling put at the top of every diagram
    vocabulary      built-in types and collection wrappers
    hidden_bases    base classes never drawn as an inheritance arrow
    """
    name: str
    source_suffix: str
    views_dir: str
    skinparam_lines: list[str]
    vocabulary: TypeVocabulary
    hidden_bases: frozenset[str] = frozenset()

    @abstractmethod
    def parse_file(self, stem: str, source: str) -> ParsedFile:
        """Parse one source file's text. Return a ParsedFile with no
        declarations when the file declares no type."""

    def enclosing_packages(self, package: str | None) -> list[str | None]:
        """Packages whose types this package sees without an import,
        closest first."""
        return [package]

    def class_stereotype(self, declaration: TypeDecl) -> str | None:
        """None: the class is drawn without a stereotype."""
        if declaration.kind in _KIND_STEREOTYPES:
            return _KIND_STEREOTYPES[declaration.kind]
        if declaration.is_abstract:
            return ABSTRACT_STEREOTYPE
        if declaration.is_static:
            return STATIC_STEREOTYPE
        return None

    def relation_policy(self, parsed_files: list[ParsedFile]) -> RelationPolicy:
        """Built once per run, after every file is parsed, so a policy may
        depend on the whole project."""
        return RelationPolicy()
