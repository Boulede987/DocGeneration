"""The UML model every language translates its source into: classifiers
with members, grouped in packages. SourceText is what a language parser
receives; ParsedFile is what it produces. Nothing here describes a source
language: how a language reads code and infers relations stays in that
language (or in a toolkit it chooses)."""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Generic, TypeVar

TYPE_PARAMETERS_START = "<"
FactsT = TypeVar("FactsT")


def bare_type_name(type_text: str) -> str:
    """'Foo<T>' -> 'Foo'. PlantUML registers 'class Foo<T>' as 'Foo', so
    every relation must reference the bare name."""
    return type_text.split(TYPE_PARAMETERS_START)[0]


class TypeKind(Enum):
    """UML classifier kinds. Language-specific kinds (record, struct,
    module, trait...) are drawn as one of these with a stereotype."""
    CLASS = "class"
    INTERFACE = "interface"
    ENUM = "enum"


class Visibility(Enum):
    """Values are the PlantUML visibility symbols."""
    PUBLIC = "+"
    PRIVATE = "-"
    PROTECTED = "#"
    PACKAGE = "~"


class MemberKind(Enum):
    FIELD = "field"
    PROPERTY = "property"
    METHOD = "method"


@dataclass
class Member:
    """One rendered member line. 'type' is the display text: a field's type,
    or a method's return type — None when shown without one."""
    kind: MemberKind
    name: str
    visibility: Visibility
    is_static: bool
    is_abstract: bool
    type: str | None
    params: list[str]


@dataclass
class TypeDecl:
    """One UML classifier. stereotype is the language's label for what it
    really is ('<<record>>', '<<module>>'...), None for a plain class; enums
    and interfaces always show their own."""
    name: str
    kind: TypeKind
    stereotype: str | None = None
    is_abstract: bool = False
    members: list[Member] = field(default_factory=list)
    enum_values: list[str] = field(default_factory=list)

    @property
    def bare_name(self) -> str:
        return bare_type_name(self.name)


@dataclass(frozen=True)
class SourceText:
    """One source file as a language parser receives it. relative_path is
    relative to the source root it was found under."""
    relative_path: Path
    text: str

    @property
    def stem(self) -> str:
        return self.relative_path.stem


@dataclass
class ResolutionHints:
    """What a file says about where the names it uses come from.
    type_imports: simple name -> package, for imports naming one type.
    namespace_imports: packages imported whole (their types all visible)."""
    type_imports: dict[str, str] = field(default_factory=dict)
    namespace_imports: set[str] = field(default_factory=set)


@dataclass(eq=False)
class ParsedFile(Generic[FactsT]):
    """'package' is the file's grouping unit (Java package, C# namespace,
    Python folder...), None when the file declares none. facts: whatever
    the language keeps from parsing to compute relations later; the core
    never reads it. notes: non-fatal warnings, reported per file.
    Compared and hashed by identity: a file is one parse result."""
    stem: str
    package: str | None
    declarations: list[TypeDecl]
    hints: ResolutionHints = field(default_factory=ResolutionHints)
    facts: FactsT | None = None
    notes: list[str] = field(default_factory=list)
