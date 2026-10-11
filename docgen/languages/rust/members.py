"""Rust fields, methods, consts and statics -> UML members: visibility,
static-ness (no self receiver), displayed types."""

from typing import TYPE_CHECKING

from docgen.core.model import Member, MemberKind, Visibility
from docgen.oo.vocabulary import TypeVocabulary

from .facts import HeldType
from .ownership import held_types
from .syntax import ATTRIBUTE, COMMENTS, display_text, field, named_children, node_text

if TYPE_CHECKING:
    from tree_sitter import Node

FUNCTION = "function_item"
NAMED_FIELDS = "field_declaration_list"
FIELD_DECLARATION = "field_declaration"
PARAMETER = "parameter"
SELF_PARAMETER = "self_parameter"
VISIBILITY = "visibility_modifier"
NOT_FIELD_TYPES = COMMENTS | {ATTRIBUTE, VISIBILITY}
PUBLIC = "pub"
MODULE_PRIVATE = "pub(self)"


def visibility_of_modifier(modifier: "Node | None") -> Visibility:
    """pub -> public; pub(crate), pub(super), pub(in path) -> package;
    nothing or pub(self) -> private to the module."""
    if modifier is None or node_text(modifier).replace(" ", "") == MODULE_PRIVATE:
        return Visibility.PRIVATE
    return Visibility.PUBLIC if node_text(modifier) == PUBLIC else Visibility.PACKAGE

def visibility(item: "Node") -> Visibility:
    return visibility_of_modifier(next(iter(named_children(item, VISIBILITY)), None))

def _field_member(name: str, type_node: "Node", visibility: Visibility, vocabulary: TypeVocabulary) -> Member:
    return Member(
        kind=MemberKind.FIELD, name=name, visibility=visibility, is_static=False, is_abstract=False,
        type=vocabulary.uml_type(display_text(type_node)), params=[],
    )

def _named_fields(body: "Node", vocabulary: TypeVocabulary) -> tuple[list[Member], list[HeldType]]:
    declarations = named_children(body, FIELD_DECLARATION)
    members = [
        _field_member(node_text(field(declaration, "name")), field(declaration, "type"), visibility(declaration),
                      vocabulary)
        for declaration in declarations
    ]
    return members, [held for declaration in declarations for held in held_types(field(declaration, "type"))]

def _tuple_fields(body: "Node", vocabulary: TypeVocabulary) -> tuple[list[Member], list[HeldType]]:
    """Fields numbered from 0, as Rust names them; a visibility modifier
    applies to the type right after it."""
    members: list[Member] = []
    held: list[HeldType] = []
    modifier: "Node | None" = None
    for child in named_children(body):
        if child.type == VISIBILITY:
            modifier = child
        elif child.type not in NOT_FIELD_TYPES:
            members.append(_field_member(str(len(members)), child, visibility_of_modifier(modifier), vocabulary))
            held += held_types(child)
            modifier = None
    return members, held

def fields(body: "Node | None", vocabulary: TypeVocabulary) -> tuple[list[Member], list[HeldType]]:
    if body is None:
        return [], []
    return _named_fields(body, vocabulary) if body.type == NAMED_FIELDS else _tuple_fields(body, vocabulary)

def _is_static(function: "Node") -> bool:
    """No self receiver: called on the type, not on a value."""
    return not named_children(field(function, "parameters"), SELF_PARAMETER)

def function_member(function: "Node", visibility: Visibility) -> Member:
    returned = field(function, "return_type")
    return Member(
        kind=MemberKind.METHOD, name=node_text(field(function, "name")), visibility=visibility,
        is_static=_is_static(function), is_abstract=False,
        type=display_text(returned) if returned is not None else None,
        params=[
            display_text(type_node)
            for parameter in named_children(field(function, "parameters"), PARAMETER)
            if (type_node := field(parameter, "type")) is not None
        ],
    )

def value_member(item: "Node", visibility: Visibility) -> Member:
    """A const or static: a static field, like a class constant."""
    type_node = field(item, "type")
    return Member(
        kind=MemberKind.FIELD, name=node_text(field(item, "name")), visibility=visibility, is_static=True,
        is_abstract=False, type=display_text(type_node) if type_node is not None else None, params=[],
    )

def free_item_member(item: "Node") -> Member:
    if item.type == FUNCTION:
        return function_member(item, visibility(item))
    return value_member(item, visibility(item))
