"""Rust items -> UML declarations and the facts linking needs: structs
(classes), enums, traits (interfaces), impl blocks (kept for linking), and
free functions, constants and statics (one <<module>> box per file)."""

from dataclasses import dataclass, field as dataclass_field
from typing import TYPE_CHECKING

from docgen.core.model import TypeDecl, TypeKind, Visibility
from docgen.oo.stereotypes import MODULE_STEREOTYPE
from docgen.oo.vocabulary import TypeVocabulary

from .facts import ImplBlock, ItemUse, RustFacts, RustTypeFacts, UseBinding
from .members import (
    FIELD_DECLARATION, FUNCTION, NAMED_FIELDS, NOT_FIELD_TYPES, fields, free_item_member,
    function_member, value_member, visibility,
)
from .modules import MODULE_SEPARATOR
from .ownership import GENERIC_TYPE, held_types
from .references import item_uses, type_names
from .syntax import NAMED_TYPE_NODES, display_text, field, is_test_only, named_children, node_text

if TYPE_CHECKING:
    from tree_sitter import Node

STRUCT = "struct_item"
ENUM = "enum_item"
TRAIT = "trait_item"
IMPL = "impl_item"
MODULE = "mod_item"
FUNCTION_SIGNATURE = "function_signature_item"
CONSTANT = "const_item"
STATIC = "static_item"
FUNCTIONS = frozenset({FUNCTION, FUNCTION_SIGNATURE})
VALUES = frozenset({CONSTANT, STATIC})
FREE_ITEMS = frozenset({FUNCTION}) | VALUES
ENUM_VARIANT = "enum_variant"
TYPE_PARAMETER_NODES = frozenset({"type_parameter", "const_parameter", "type_identifier"})
ROOT_BOX_NAME = "crate"
MODULE_BOX_SUFFIX = "_module"


@dataclass
class ParsedItems:
    """declarations[i] is described by facts.types[i]."""
    declarations: list[TypeDecl] = dataclass_field(default_factory=list)
    facts: RustFacts = dataclass_field(default_factory=lambda: RustFacts(module_path=None))

    def add(self, declaration: TypeDecl, type_facts: RustTypeFacts) -> None:
        self.declarations.append(declaration)
        self.facts.types.append(type_facts)


@dataclass
class CodeFacts:
    """What a group of functions and values mentions."""
    signature_types: list[str]
    body_types: list[str]
    item_uses: list[ItemUse]






def _declared_name(item: "Node") -> str:
    """Name with its type parameters, lifetimes left out: Wrapper<T>."""
    name = node_text(field(item, "name"))
    parameters = [
        node_text(field(parameter, "name") if field(parameter, "name") is not None else parameter)
        for parameter in named_children(field(item, "type_parameters"))
        if parameter.type in TYPE_PARAMETER_NODES
    ]
    return f"{name}<{', '.join(parameters)}>" if parameters else name
















def _code_facts(items: list["Node"], uses: list[UseBinding]) -> CodeFacts:
    """Functions contribute their signatures and bodies; consts and statics
    their type and value."""
    return CodeFacts(
        signature_types=[name for item in items for part in _signature_parts(item) for name in type_names(part)],
        body_types=[name for item in items for name in type_names(_code_part(item))],
        item_uses=[
            use for item in items
            for use in item_uses(item if item.type in FUNCTIONS else field(item, "value"), uses)
        ],
    )


def _signature_parts(item: "Node") -> list["Node | None"]:
    if item.type in FUNCTIONS:
        return [field(item, "parameters"), field(item, "return_type")]
    return [field(item, "type")]


def _code_part(item: "Node") -> "Node | None":
    return field(item, "body") if item.type in FUNCTIONS else field(item, "value")


def _struct(item: "Node", vocabulary: TypeVocabulary) -> tuple[TypeDecl, RustTypeFacts]:
    members, held = fields(field(item, "body"), vocabulary)
    declaration = TypeDecl(name=_declared_name(item), kind=TypeKind.CLASS, members=members)
    return declaration, RustTypeFacts(name=declaration.bare_name, fields=held)


def _variant_field_types(body: "Node") -> list["Node"]:
    if body.type == NAMED_FIELDS:
        return [type_node for declaration in named_children(body, FIELD_DECLARATION)
                if (type_node := field(declaration, "type")) is not None]
    return [child for child in named_children(body) if child.type not in NOT_FIELD_TYPES]


def _enum(item: "Node") -> tuple[TypeDecl, RustTypeFacts]:
    """Variant data is held like fields: an enum owns what its variants carry."""
    variants = named_children(field(item, "body"), ENUM_VARIANT)
    declaration = TypeDecl(
        name=_declared_name(item), kind=TypeKind.ENUM,
        enum_values=[node_text(field(variant, "name")) for variant in variants],
    )
    held = [
        held_type
        for variant in variants
        if (body := field(variant, "body")) is not None
        for type_node in _variant_field_types(body)
        for held_type in held_types(type_node)
    ]
    return declaration, RustTypeFacts(name=declaration.bare_name, fields=held)


def _trait(item: "Node", uses: list[UseBinding]) -> tuple[TypeDecl, RustTypeFacts]:
    """Trait methods are public: a trait has no private items."""
    functions = [child for child in named_children(field(item, "body")) if child.type in FUNCTIONS]
    declaration = TypeDecl(
        name=_declared_name(item), kind=TypeKind.INTERFACE,
        members=[function_member(function, Visibility.PUBLIC) for function in functions],
    )
    code = _code_facts(functions, uses)
    facts = RustTypeFacts(
        name=declaration.bare_name, supertraits=type_names(field(item, "bounds")),
        signature_types=code.signature_types, body_types=code.body_types, item_uses=code.item_uses,
    )
    return declaration, facts


def _type_path(node: "Node") -> "Node":
    """The type itself, without its arguments: Foo for Foo<T>."""
    base = field(node, "type") if node.type == GENERIC_TYPE else None
    return base if base is not None else node


def _type_parameter_names(item: "Node") -> set[str]:
    return {
        node_text(field(parameter, "name") if field(parameter, "name") is not None else parameter)
        for parameter in named_children(field(item, "type_parameters"))
    }


def _impl_target(item: "Node") -> str | None:
    """The implemented type's path: Foo, a::Foo, Foo for Foo<T>. None for
    a blanket impl on one of the impl's own type parameters (impl<T> Tr
    for T): it is no single type. Other shapes (u32, &Foo, dyn Tr) are
    kept as written: they are not crate types, and are noted as such."""
    written = field(item, "type")
    if written is None:
        return None
    target = _type_path(written)
    if target.type in NAMED_TYPE_NODES and node_text(target) in _type_parameter_names(item):
        return None
    return display_text(target)


def _impl(item: "Node", uses: list[UseBinding]) -> ImplBlock | None:
    """Methods of a trait impl are public: they are the trait's.
    Associated consts become static members."""
    target = _impl_target(item)
    if target is None:
        return None
    trait = field(item, "trait")
    is_trait_impl = trait is not None
    items = [child for child in named_children(field(item, "body")) if child.type in (FUNCTION, CONSTANT)]
    code = _code_facts(items, uses)
    return ImplBlock(
        target=target,
        trait=display_text(_type_path(trait)) if trait is not None else None,
        members=[
            (function_member if child.type == FUNCTION else value_member)(
                child, Visibility.PUBLIC if is_trait_impl else visibility(child),
            )
            for child in items
        ],
        signature_types=code.signature_types, body_types=code.body_types, item_uses=code.item_uses,
    )




def _items_of(container: "Node", inline_modules: list[str], prefix: str = "") -> list["Node"]:
    """Items of the file and of its inline modules (drawn in the file's
    module, whose paths are recorded), test-only modules and items left
    out."""
    items: list["Node"] = []
    for child in named_children(container):
        if is_test_only(child):
            continue
        body = field(child, "body") if child.type == MODULE else None
        if body is not None:
            path = prefix + node_text(field(child, "name"))
            inline_modules.append(path)
            items += _items_of(body, inline_modules, path + MODULE_SEPARATOR)
        elif child.type != MODULE:
            items.append(child)
    return items


def _box_name(module_path: str | None, type_names_in_file: set[str]) -> str:
    """The module's name, so the box reads like the module; suffixed when a
    type of the file has the same name, so the two never merge."""
    name = module_path.split(MODULE_SEPARATOR)[-1] if module_path else ROOT_BOX_NAME
    return name + MODULE_BOX_SUFFIX if name in type_names_in_file else name


def _module_box(free_items: list["Node"], box_name: str, uses: list[UseBinding]) -> tuple[TypeDecl, RustTypeFacts]:
    declaration = TypeDecl(
        name=box_name, kind=TypeKind.CLASS, stereotype=MODULE_STEREOTYPE,
        members=[free_item_member(item) for item in free_items],
    )
    code = _code_facts(free_items, uses)
    return declaration, RustTypeFacts(
        name=box_name, signature_types=code.signature_types, body_types=code.body_types, item_uses=code.item_uses,
    )


def parse_items(
    root: "Node", module_path: str | None, uses: list[UseBinding], vocabulary: TypeVocabulary,
) -> ParsedItems:
    parsed = ParsedItems(facts=RustFacts(module_path=module_path, uses=uses))
    free_items: list["Node"] = []
    for item in _items_of(root, parsed.facts.inline_modules):
        if item.type == STRUCT:
            parsed.add(*_struct(item, vocabulary))
        elif item.type == ENUM:
            parsed.add(*_enum(item))
        elif item.type == TRAIT:
            parsed.add(*_trait(item, uses))
        elif item.type == IMPL and (impl_block := _impl(item, uses)) is not None:
            parsed.facts.impl_blocks.append(impl_block)
        elif item.type in FREE_ITEMS:
            free_items.append(item)
    if free_items:
        box_name = _box_name(module_path, {declaration.bare_name for declaration in parsed.declarations})
        parsed.add(*_module_box(free_items, box_name, uses))
        parsed.facts.box_name = box_name
    return parsed
