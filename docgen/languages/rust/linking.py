"""Linking the crate once every file is parsed (flow:
docs/Algorithms/rust_link.puml): impl blocks join their type, wherever it
is declared, then each declared type's relations are computed. Every
relation carries its target's module: the crate index already knows it."""

from dataclasses import dataclass, field
from typing import Generic, TypeVar

from docgen.core.model import ParsedFile
from docgen.core.project import Project
from docgen.core.relations import (
    ASSOCIATES, COMPOSES, DEPENDS, INHERITS, MANY, REALIZES, Relation, RelationLevel,
)

from .facts import HeldType, ImplBlock, ItemUse, Ownership, RustFacts
from .index import CrateIndex, TypeRef

ReferenceT = TypeVar("ReferenceT")


@dataclass(frozen=True)
class Located(Generic[ReferenceT]):
    """A reference with the file it was written in: names resolve from
    that file's module and use declarations."""
    reference: ReferenceT
    context: RustFacts


@dataclass
class TypeLinks:
    """Everything a declared type refers to, from its own file and from
    impl blocks anywhere in the crate."""
    supertraits: list[Located[str]] = field(default_factory=list)
    realized_traits: list[Located[str]] = field(default_factory=list)
    held: list[Located[HeldType]] = field(default_factory=list)
    used_types: list[Located[str]] = field(default_factory=list)
    item_uses: list[Located[ItemUse]] = field(default_factory=list)


def _own_links(project: Project[RustFacts]) -> dict[TypeRef, TypeLinks]:
    links: dict[TypeRef, TypeLinks] = {}
    for parsed in project.files:
        facts = parsed.facts
        if facts is None:
            continue
        for declaration, type_facts in zip(parsed.declarations, facts.types, strict=True):
            links[TypeRef(facts.module_path, declaration.bare_name)] = TypeLinks(
                supertraits=[Located(text, facts) for text in type_facts.supertraits],
                held=[Located(held, facts) for held in type_facts.fields],
                used_types=[Located(text, facts) for text in type_facts.signature_types + type_facts.body_types],
                item_uses=[Located(use, facts) for use in type_facts.item_uses],
            )
    return links


def _merge(impl_block: ImplBlock, facts: RustFacts, type_links: TypeLinks) -> None:
    if impl_block.trait is not None:
        type_links.realized_traits.append(Located(impl_block.trait, facts))
    type_links.used_types += [Located(text, facts) for text in impl_block.signature_types + impl_block.body_types]
    type_links.item_uses += [Located(use, facts) for use in impl_block.item_uses]


def merge_impls(project: Project[RustFacts], index: CrateIndex) -> dict[TypeRef, TypeLinks]:
    """Adds each impl block's methods to its type, and its references to
    the type's links. An impl of a type outside the crate becomes a note on
    the impl's file. Runs once per link: it extends the declarations."""
    links = _own_links(project)
    for parsed in project.files:
        facts = parsed.facts
        if facts is None:
            continue
        for impl_block in facts.impl_blocks:
            target = index.resolve_type(impl_block.target, facts)
            declared = index.declared(target) if target is not None else None
            if target is None or declared is None:
                parsed.notes.append(f"impl {impl_block.target}: type not in the crate")
                continue
            declared.declaration.members.extend(impl_block.members)
            _merge(impl_block, facts, links[target])
    return links


class _RelationSet:
    """One relation per (arrow, target), in the order first found."""

    def __init__(self, source: TypeRef):
        self.source = source
        self.relations: dict[tuple[str, TypeRef], Relation] = {}

    def add(self, arrow: str, target: TypeRef, level: RelationLevel, multiplicity: str | None = None) -> None:
        if (arrow, target) not in self.relations:
            self.relations[(arrow, target)] = Relation(
                self.source.name, arrow, target.name, level, multiplicity, target_package=target.module,
            )

    def targets(self) -> set[TypeRef]:
        return {target for _arrow, target in self.relations}


def _add_inheritance(found: _RelationSet, links: TypeLinks, index: CrateIndex) -> None:
    for arrow, traits in ((INHERITS, links.supertraits), (REALIZES, links.realized_traits)):
        for trait in traits:
            if (target := index.resolve_type(trait.reference, trait.context)) is not None:
                found.add(arrow, target, RelationLevel.INHERITANCE)


def _add_held(found: _RelationSet, links: TypeLinks, index: CrateIndex) -> None:
    """Owned: the holder controls the value's lifetime (composition);
    shared through a reference or a counted pointer: association. A type
    may hold itself (Box<Node>, Weak<Category>)."""
    for held in links.held:
        target = index.resolve_type(held.reference.name, held.context)
        if target is None:
            continue
        if held.reference.ownership is Ownership.OWNED:
            arrow, level = COMPOSES, RelationLevel.STRONG
        else:
            arrow, level = ASSOCIATES, RelationLevel.WEAK
        found.add(arrow, target, level, MANY if held.reference.is_collection else None)


def _add_dependencies(found: _RelationSet, links: TypeLinks, index: CrateIndex) -> None:
    """Weakest last: a type already held or inherited isn't also a
    dependency, and nothing depends on itself."""
    related = found.targets() | {found.source}
    for used in links.used_types:
        target = index.resolve_type(used.reference, used.context)
        if target is not None and target not in related:
            found.add(DEPENDS, target, RelationLevel.WEAK)
    for use in links.item_uses:
        module_box = index.resolve_item(use.reference, use.context)
        if module_box is not None and module_box != found.source:
            found.add(DEPENDS, module_box, RelationLevel.WEAK)


def file_relations(parsed: ParsedFile[RustFacts], links: dict[TypeRef, TypeLinks], index: CrateIndex) -> list[Relation]:
    """Each declared type's relations, from links completed by merge_impls."""
    facts = parsed.facts
    if facts is None:
        return []
    relations: list[Relation] = []
    for declaration in parsed.declarations:
        source = TypeRef(facts.module_path, declaration.bare_name)
        found = _RelationSet(source)
        _add_inheritance(found, links[source], index)
        _add_held(found, links[source], index)
        _add_dependencies(found, links[source], index)
        relations += found.relations.values()
    return relations
