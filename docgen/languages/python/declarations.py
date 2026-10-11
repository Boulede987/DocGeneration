"""Python classes and modules -> UML declarations, each with the facts
relation inference needs (bases, usages, other modules' names used)."""

import ast
from dataclasses import dataclass, field
from typing import Iterator

from docgen.core.model import TypeDecl, TypeKind
from docgen.oo.facts import TypeFacts
from docgen.oo.language import DeclarationWithFacts
from docgen.oo.stereotypes import ABSTRACT_MODIFIER, MODULE_STEREOTYPE, class_stereotype, is_abstract
from docgen.oo.vocabulary import TypeVocabulary

from . import usages
from .members import has_abstract_method, members_of, module_members
from .modules import ImportedNames, ModuleUse
from .syntax import decorator_names, simple_name
from .vocabulary import DATACLASS_STYLE

ENUM_BASES = frozenset({"Enum", "IntEnum", "StrEnum", "Flag", "IntFlag"})
PROTOCOL_BASE = "Protocol"
ABSTRACT_BASE = "ABC"
GENERIC_BASE = "Generic"
OBJECT_BASE = "object"
DATACLASS_MODIFIER = "dataclass"
DATACLASS_STEREOTYPE = f"<<{DATACLASS_STYLE.stereotype}>>"
_ENUM_CONFIGURATION_PREFIX = "_"


@dataclass
class PythonTypeFacts(TypeFacts):
    """module_uses: other modules' top-level names the declaration's code
    reads. module_path: set on a module box only, the path Python imports
    its module by."""
    module_uses: list[ModuleUse] = field(default_factory=list)
    module_path: str | None = None


@dataclass(frozen=True)
class ModuleIdentity:
    box_name: str
    module_path: str | None


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
    modifiers: set[str] = set()
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


def _stereotype(modifiers: frozenset[str]) -> str | None:
    """A dataclass shows <<dataclass>> even when abstract: a box has one
    stereotype, and being a dataclass says more about how it's used."""
    return DATACLASS_STEREOTYPE if DATACLASS_MODIFIER in modifiers else class_stereotype(modifiers)


def _declaration(class_node: ast.ClassDef, vocabulary: TypeVocabulary, imported: ImportedNames) -> DeclarationWithFacts:
    """Bases are kept as declared, first one as base class, including the
    ones never drawn (object, ABC, Generic...). Enums and protocols get no
    usage facts: what they mention is not a use."""
    bases = base_names(class_node)
    modifiers = _modifiers(class_node, bases)
    kind = _kind(bases)
    declaration = TypeDecl(
        name=class_node.name, kind=kind, stereotype=_stereotype(modifiers), is_abstract=is_abstract(modifiers),
    )
    facts = PythonTypeFacts(name=class_node.name, base_class=bases[0] if bases else None, additional_bases=bases[1:])
    if kind is TypeKind.ENUM:
        declaration.enum_values = _enum_values(class_node)
        return declaration, facts
    declaration.members = members_of(class_node, vocabulary)
    if kind is TypeKind.INTERFACE:
        return declaration, facts
    facts.field_usages = usages.field_usages(class_node)
    facts.signature_types = usages.signature_types(class_node)
    facts.body_types = usages.body_types(class_node)
    facts.newed_types = usages.newed_types(class_node)
    facts.module_uses = usages.module_uses([class_node], imported)
    return declaration, facts


def class_declarations(
    tree: ast.Module, vocabulary: TypeVocabulary, imported: ImportedNames,
) -> list[DeclarationWithFacts]:
    return [_declaration(class_node, vocabulary, imported) for class_node in _classes_in(tree.body)]


def module_declaration(
    tree: ast.Module, identity: ModuleIdentity, vocabulary: TypeVocabulary, imported: ImportedNames,
) -> DeclarationWithFacts | None:
    """The module's free functions and variables as one <<module>> box, so
    what they use shows up as dependencies like any class's. None: nothing
    to draw (the module has only classes and imports)."""
    members = module_members(tree, vocabulary)
    if not members:
        return None
    # UML has no module classifier: a class box, told apart by its stereotype.
    declaration = TypeDecl(name=identity.box_name, kind=TypeKind.CLASS, stereotype=MODULE_STEREOTYPE, members=members)
    facts = PythonTypeFacts(
        name=identity.box_name,
        signature_types=usages.module_signature_types(tree),
        body_types=usages.module_body_types(tree),
        module_uses=usages.module_uses(usages.module_scopes(tree), imported),
        module_path=identity.module_path,
    )
    return declaration, facts
