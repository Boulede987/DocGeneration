"""Python classes -> TypeDecl: kind, modifiers, bases, members, usages."""

import ast
from typing import Iterator

from docgen.core.model import ABSTRACT_MODIFIER, TypeDecl, TypeKind
from docgen.core.vocabulary import TypeVocabulary

from . import usages
from .members import has_abstract_method, members_of
from .syntax import decorator_names, simple_name

ENUM_BASES = frozenset({"Enum", "IntEnum", "StrEnum", "Flag", "IntFlag"})
PROTOCOL_BASE = "Protocol"
ABSTRACT_BASE = "ABC"
GENERIC_BASE = "Generic"
OBJECT_BASE = "object"
DATACLASS_MODIFIER = "dataclass"
_ENUM_CONFIGURATION_PREFIX = "_"


def _classes_in(statements: list[ast.stmt]) -> Iterator[ast.ClassDef]:
    """Classes in source order, nested classes right after their owner.
    Classes defined inside functions are local details and skipped."""
    for statement in statements:
        if isinstance(statement, ast.ClassDef):
            yield statement
            yield from _classes_in(statement.body)


def base_names(class_node: ast.ClassDef) -> list[str]:
    """Simple name of each base, in source order ('base.Entity' -> 'Entity',
    'Generic[T]' -> 'Generic')."""
    return [name for base in class_node.bases if (name := simple_name(base)) is not None]


def _kind(bases: list[str]) -> TypeKind:
    if ENUM_BASES & set(bases):
        return TypeKind.ENUM
    if PROTOCOL_BASE in bases:
        return TypeKind.INTERFACE
    return TypeKind.CLASS


def _modifiers(class_node: ast.ClassDef, bases: list[str]) -> frozenset[str]:
    modifiers = set()
    if ABSTRACT_BASE in bases or has_abstract_method(class_node):
        modifiers.add(ABSTRACT_MODIFIER)
    if DATACLASS_MODIFIER in decorator_names(class_node):
        modifiers.add(DATACLASS_MODIFIER)
    return frozenset(modifiers)


def _enum_member_names(statement: ast.stmt) -> list[str]:
    """Names a body statement makes Enum members: assignments only — a bare
    annotation ('note: str') declares no member."""
    if isinstance(statement, ast.Assign):
        return [target.id for target in statement.targets if isinstance(target, ast.Name)]
    if isinstance(statement, ast.AnnAssign) and statement.value is not None and isinstance(statement.target, ast.Name):
        return [statement.target.id]
    return []


def _enum_values(class_node: ast.ClassDef) -> list[str]:
    """Underscore names (_ignore_, _order_...) configure the Enum and are
    not members."""
    names = [name for statement in class_node.body for name in _enum_member_names(statement)]
    return [name for name in names if not name.startswith(_ENUM_CONFIGURATION_PREFIX)]


def _declaration(class_node: ast.ClassDef, vocabulary: TypeVocabulary) -> TypeDecl:
    """Bases are kept as declared, first one as base class, including the
    ones never drawn (object, ABC, Generic...)."""
    bases = base_names(class_node)
    declaration = TypeDecl(
        name=class_node.name,
        kind=_kind(bases),
        modifiers=_modifiers(class_node, bases),
        base_class=bases[0] if bases else None,
        additional_bases=bases[1:],
    )
    if declaration.kind is TypeKind.ENUM:
        declaration.enum_values = _enum_values(class_node)
        return declaration
    declaration.members = members_of(class_node, vocabulary)
    declaration.field_usages = usages.field_usages(class_node)
    declaration.signature_types = usages.signature_types(class_node)
    declaration.body_types = usages.body_types(class_node)
    declaration.newed_types = usages.newed_types(class_node)
    return declaration


def class_declarations(tree: ast.Module, vocabulary: TypeVocabulary) -> list[TypeDecl]:
    return [_declaration(class_node, vocabulary) for class_node in _classes_in(tree.body)]
