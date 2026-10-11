"""What an object-oriented parser records about each declared type so that
relations can be inferred once the whole project is known."""

from dataclasses import dataclass, field

from docgen.core.model import bare_type_name


@dataclass
class FieldUsage:
    """A type held by a field, property or record component, as written in
    source (e.g. 'List<Item>')."""
    type_text: str
    is_public: bool
    is_serialized: bool


@dataclass
class TypeFacts:
    """One declared type's inheritance and usages. Type texts stay as
    written in source; simple names are derived from them on demand. A type
    whose parser fills no usage list gets no usage relations (enums and
    interfaces, in the languages using this toolkit).
    additional_bases: further superclasses, for multiple inheritance, in
    declaration order after base_class."""
    name: str
    base_class: str | None = None
    additional_bases: list[str] = field(default_factory=list)
    interfaces: list[str] = field(default_factory=list)
    field_usages: list[FieldUsage] = field(default_factory=list)
    signature_types: list[str] = field(default_factory=list)
    body_types: list[str] = field(default_factory=list)
    newed_types: list[str] = field(default_factory=list)

    @property
    def bare_name(self) -> str:
        return bare_type_name(self.name)
