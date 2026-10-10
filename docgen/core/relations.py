"""Relations between declared types: inheritance from each declaration's
bases, and usage (composition / association / dependency) from the type
texts its members hold or mention."""

from dataclasses import dataclass
from enum import IntEnum

from .model import TypeDecl, bare_type_name
from .vocabulary import TypeVocabulary

INHERITS = "--|>"
REALIZES = "..|>"
COMPOSES = "*-->"
ASSOCIATES = "-->"
DEPENDS = "..>"
MANY = '"0..*"'


class RelationLevel(IntEnum):
    """Strength order: INHERITANCE < STRONG < WEAK."""
    INHERITANCE = 0
    STRONG = 1
    WEAK = 2


@dataclass(frozen=True)
class Relation:
    """Ends are bare simple names, never package-qualified."""
    source: str
    arrow: str
    target: str
    level: RelationLevel
    multiplicity: str | None = None

    def render(self, qualified_source: str, qualified_target: str) -> str:
        """The PlantUML line, with the ends as the caller qualified them."""
        multiplicity = f" {self.multiplicity}" if self.multiplicity else ""
        return f"{qualified_source} {self.arrow}{multiplicity} {qualified_target}"


@dataclass(frozen=True)
class FieldFacts:
    """Everything known about one project type held by a declaration's
    fields — merged across all fields holding it."""
    target: str
    is_collection: bool
    is_public: bool
    is_serialized: bool
    is_newed: bool


class RelationPolicy:
    """Composition: instantiated by the holder, or exposed publicly.
    Association: any other held type."""

    def classify_field(self, facts: FieldFacts) -> tuple[str, RelationLevel]:
        if facts.is_newed or facts.is_public:
            return COMPOSES, RelationLevel.STRONG
        return ASSOCIATES, RelationLevel.WEAK


def _superclasses(declaration: TypeDecl) -> list[str]:
    """Bare names, base class first, each once: arrow order follows the
    declaration."""
    primary_base = [declaration.base_class] if declaration.base_class else []
    return list(dict.fromkeys(bare_type_name(base) for base in primary_base + declaration.additional_bases))


def inherited_names(declaration: TypeDecl) -> set[str]:
    return set(_superclasses(declaration)) | {bare_type_name(interface) for interface in declaration.interfaces}


def inheritance_relations(declaration: TypeDecl, hidden_bases: frozenset[str]) -> list[Relation]:
    """A hidden base draws no arrow (it still counts as inherited, so it is
    never reported again as a usage)."""
    source = declaration.bare_name
    relations: list[Relation] = []
    for base in _superclasses(declaration):
        if base not in hidden_bases:
            relations.append(Relation(source, INHERITS, base, RelationLevel.INHERITANCE))
    for interface in declaration.interfaces:
        relations.append(Relation(source, REALIZES, bare_type_name(interface), RelationLevel.INHERITANCE))
    return relations


def _merge(previous: FieldFacts | None, name: str, *, is_collection: bool, is_public: bool,
           is_serialized: bool, is_newed: bool) -> FieldFacts:
    """Per-field facts are OR-ed; is_newed describes the type in the whole
    declaration (not one field), so it's the same for every field."""
    if previous is None:
        return FieldFacts(
            target=name, is_collection=is_collection, is_public=is_public,
            is_serialized=is_serialized, is_newed=is_newed,
        )
    return FieldFacts(
        target=name,
        is_collection=previous.is_collection or is_collection,
        is_public=previous.is_public or is_public,
        is_serialized=previous.is_serialized or is_serialized,
        is_newed=previous.is_newed,
    )


def _merged_field_facts(
    declaration: TypeDecl,
    candidates: set[str],
    vocabulary: TypeVocabulary,
) -> dict[str, FieldFacts]:
    """Project types held by the declaration's fields, one FieldFacts each."""
    newed = {name for text in declaration.newed_types for name in vocabulary.type_names(text)}
    facts: dict[str, FieldFacts] = {}
    for usage in declaration.field_usages:
        is_collection = vocabulary.is_collection(usage.type_text)
        for name in vocabulary.type_names(usage.type_text) & candidates:
            facts[name] = _merge(
                facts.get(name), name, is_collection=is_collection, is_public=usage.is_public,
                is_serialized=usage.is_serialized, is_newed=name in newed,
            )
    return facts


def usage_relations(
    declaration: TypeDecl,
    known_types: set[str],
    already_inherited: set[str],
    policy: RelationPolicy,
    vocabulary: TypeVocabulary,
) -> list[Relation]:
    """Field relations (classified by policy), then dependencies on types
    only mentioned in signatures or method bodies; each group sorted by
    name, levels possibly interleaved."""
    if not declaration.has_usages:
        return []
    source = declaration.bare_name
    candidates = known_types - already_inherited - {source}
    field_facts = _merged_field_facts(declaration, candidates, vocabulary)

    relations: list[Relation] = []
    for name in sorted(field_facts):
        facts = field_facts[name]
        arrow, level = policy.classify_field(facts)
        relations.append(Relation(source, arrow, name, level, MANY if facts.is_collection else None))

    mentioned = {
        name
        for text in declaration.signature_types + declaration.body_types
        for name in vocabulary.type_names(text)
    }
    for name in sorted((mentioned & candidates) - set(field_facts)):
        relations.append(Relation(source, DEPENDS, name, RelationLevel.WEAK))
    return relations
