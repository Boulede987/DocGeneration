"""Object-oriented relation inference: inheritance from each type's bases,
and usage (composition / association / dependency) from the type texts its
members hold or mention."""

from dataclasses import dataclass

from docgen.core.model import bare_type_name
from docgen.core.relations import ASSOCIATES, COMPOSES, DEPENDS, INHERITS, MANY, REALIZES, Relation, RelationLevel

from .facts import TypeFacts
from .vocabulary import TypeVocabulary


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


def _superclasses(facts: TypeFacts) -> list[str]:
    """Bare names, base class first, each once: arrow order follows the
    declaration."""
    primary_base = [facts.base_class] if facts.base_class else []
    return list(dict.fromkeys(bare_type_name(base) for base in primary_base + facts.additional_bases))


def inherited_names(facts: TypeFacts) -> set[str]:
    return set(_superclasses(facts)) | {bare_type_name(interface) for interface in facts.interfaces}


def inheritance_relations(facts: TypeFacts, hidden_bases: frozenset[str]) -> list[Relation]:
    """A hidden base draws no arrow (it still counts as inherited, so it is
    never reported again as a usage)."""
    source = facts.bare_name
    relations = [
        Relation(source, INHERITS, base, RelationLevel.INHERITANCE)
        for base in _superclasses(facts)
        if base not in hidden_bases
    ]
    relations += [
        Relation(source, REALIZES, bare_type_name(interface), RelationLevel.INHERITANCE)
        for interface in facts.interfaces
    ]
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


def _merged_field_facts(facts: TypeFacts, candidates: set[str], vocabulary: TypeVocabulary) -> dict[str, FieldFacts]:
    """Project types held by the type's fields, one FieldFacts each."""
    newed = {name for text in facts.newed_types for name in vocabulary.type_names(text)}
    merged: dict[str, FieldFacts] = {}
    for usage in facts.field_usages:
        is_collection = vocabulary.is_collection(usage.type_text)
        for name in vocabulary.type_names(usage.type_text) & candidates:
            merged[name] = _merge(
                merged.get(name), name, is_collection=is_collection, is_public=usage.is_public,
                is_serialized=usage.is_serialized, is_newed=name in newed,
            )
    return merged


def usage_relations(
    facts: TypeFacts,
    known_types: set[str],
    policy: RelationPolicy,
    vocabulary: TypeVocabulary,
) -> list[Relation]:
    """Field relations (classified by policy), then dependencies on types
    only mentioned in signatures or bodies; each group sorted by name,
    levels possibly interleaved. Inherited types are never usages."""
    source = facts.bare_name
    candidates = known_types - inherited_names(facts) - {source}
    field_facts = _merged_field_facts(facts, candidates, vocabulary)

    relations: list[Relation] = []
    for name in sorted(field_facts):
        held = field_facts[name]
        arrow, level = policy.classify_field(held)
        relations.append(Relation(source, arrow, name, level, MANY if held.is_collection else None))

    mentioned = {name for text in facts.signature_types + facts.body_types for name in vocabulary.type_names(text)}
    for name in sorted((mentioned & candidates) - set(field_facts)):
        relations.append(Relation(source, DEPENDS, name, RelationLevel.WEAK))
    return relations


def relations_of(
    file_facts: list[TypeFacts],
    known_types: set[str],
    policy: RelationPolicy,
    vocabulary: TypeVocabulary,
    hidden_bases: frozenset[str],
) -> list[Relation]:
    """A file's relations: every type's inheritance first, then every
    type's usages."""
    inheritance = [relation for facts in file_facts for relation in inheritance_relations(facts, hidden_bases)]
    usages = [relation for facts in file_facts for relation in usage_relations(facts, known_types, policy, vocabulary)]
    return inheritance + usages
