"""Language-neutral description of parsed source code. Nothing after parsing
reads source text: these types are its only input."""

from dataclasses import dataclass, field
from enum import Enum

TYPE_PARAMETERS_START = "<"
ABSTRACT_MODIFIER = "abstract"
STATIC_MODIFIER = "static"


def bare_type_name(type_text: str) -> str:
    """'Foo<T>' -> 'Foo'. PlantUML registers 'class Foo<T>' as 'Foo', so
    every relation must reference the bare name."""
    return type_text.split(TYPE_PARAMETERS_START)[0]


class TypeKind(Enum):
    CLASS = "class"
    INTERFACE = "interface"
    ENUM = "enum"
    RECORD = "record"
    STRUCT = "struct"


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
    or a method's return type — None for a method shown without one."""
    kind: MemberKind
    name: str
    visibility: Visibility
    is_static: bool
    is_abstract: bool
    type: str | None
    params: list[str]


@dataclass
class FieldUsage:
    """A type held by a field, property or record component, as written in
    source (e.g. 'List<Item>')."""
    type_text: str
    is_public: bool
    is_serialized: bool


@dataclass
class TypeDecl:
    """One declared type. Type texts (base_class, interfaces, the usage
    lists) stay as written in source; simple names are derived from them on
    demand."""
    name: str
    kind: TypeKind
    modifiers: frozenset[str] = frozenset()
    base_class: str | None = None
    interfaces: list[str] = field(default_factory=list)
    members: list[Member] = field(default_factory=list)
    enum_values: list[str] = field(default_factory=list)
    field_usages: list[FieldUsage] = field(default_factory=list)
    signature_types: list[str] = field(default_factory=list)
    body_types: list[str] = field(default_factory=list)
    newed_types: list[str] = field(default_factory=list)

    @property
    def bare_name(self) -> str:
        return bare_type_name(self.name)

    @property
    def is_abstract(self) -> bool:
        return ABSTRACT_MODIFIER in self.modifiers

    @property
    def is_static(self) -> bool:
        return STATIC_MODIFIER in self.modifiers

    @property
    def has_usages(self) -> bool:
        """Enums and interfaces are drawn, but never get usage relations."""
        return self.kind not in (TypeKind.ENUM, TypeKind.INTERFACE)


@dataclass
class ResolutionHints:
    """What a file says about where the names it uses come from.
    type_imports: simple name -> package, for imports naming one type.
    namespace_imports: packages imported whole (their types all visible)."""
    type_imports: dict[str, str] = field(default_factory=dict)
    namespace_imports: set[str] = field(default_factory=set)


@dataclass
class ParsedFile:
    """'package' is the file's grouping unit (Java package, C# namespace...),
    None when the file declares none."""
    stem: str
    package: str | None
    declarations: list[TypeDecl]
    hints: ResolutionHints = field(default_factory=ResolutionHints)
