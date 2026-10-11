"""The type texts a Python class or module holds (attributes) or mentions
(signatures, function bodies, module-level assignments)."""

import ast
from typing import Iterable

from docgen.core.model import Visibility
from docgen.oo.facts import FieldUsage

from .members import CONSTRUCTOR, attributes_of, module_functions, parameter_types, return_type
from .modules import PACKAGE_SEPARATOR, ImportedNames, ModuleUse
from .syntax import FunctionNode, constructor_called, functions_of, looks_like_class_name, type_text, visibility_of


def field_usages(class_node: ast.ClassDef) -> list[FieldUsage]:
    """Typed attributes only; static class variables are constants, not
    held objects. Python has no serialization marker like Unity's
    [SerializeField], so is_serialized is always False."""
    return [
        FieldUsage(
            type_text=attribute.type_text,
            is_public=visibility_of(attribute.name) is Visibility.PUBLIC,
            is_serialized=False,
        )
        for attribute in attributes_of(class_node)
        if attribute.type_text and not attribute.is_static
    ]


def _signature_types(functions: Iterable[FunctionNode], is_method: bool) -> list[str]:
    types: list[str] = []
    for function in functions:
        types.extend(parameter_types(function, is_method=is_method))
        if (returned := return_type(function)) is not None:
            types.append(returned)
    return types


def signature_types(class_node: ast.ClassDef) -> list[str]:
    """Parameter and return types of every method but __init__ (its
    parameters are what the attributes hold, not uses)."""
    methods = (function for function in functions_of(class_node) if function.name != CONSTRUCTOR)
    return _signature_types(methods, is_method=True)


def module_signature_types(tree: ast.Module) -> list[str]:
    """Free functions have no bound first parameter: every parameter counts."""
    return _signature_types(module_functions(tree), is_method=False)


def _mentioned_type(node: ast.AST) -> str | None:
    """Without type inference, code only reveals a type where it names one:
    a constructor call Foo(...), class access Foo.x, or an annotation."""
    if called := constructor_called(node):
        return called
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and looks_like_class_name(node.value.id):
        return node.value.id
    if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        return type_text(node.annotation)
    return None


def _mentioned_in(scopes: Iterable[ast.AST]) -> list[str]:
    """Every node of every scope, nested calls and inner functions included."""
    return [mentioned for scope in scopes for node in ast.walk(scope) if (mentioned := _mentioned_type(node))]


def body_types(class_node: ast.ClassDef) -> list[str]:
    return _mentioned_in(functions_of(class_node))


def module_body_types(tree: ast.Module) -> list[str]:
    """What free functions mention, plus what top-level assignments mention
    anywhere in their annotation or value (X = f([Style(...)]) uses
    Style)."""
    return _mentioned_in(module_scopes(tree))


def module_scopes(tree: ast.Module) -> list[ast.AST]:
    """The code a module box stands for: free functions and top-level
    assignments."""
    assignments = [statement for statement in tree.body if isinstance(statement, (ast.Assign, ast.AnnAssign))]
    return [*module_functions(tree), *assignments]


def _dotted_name(node: ast.expr) -> str | None:
    """'a.b.c' for a chain of attributes on a plain name; None otherwise
    (a call's result, a subscript...)."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute) and (owner := _dotted_name(node.value)) is not None:
        return owner + PACKAGE_SEPARATOR + node.attr
    return None


def _module_use(node: ast.AST, imported: ImportedNames) -> ModuleUse | None:
    """f (an imported member), or x.f / a.b.f (an attribute of an imported
    module), when read: assigning to the name is not a use."""
    if not isinstance(node, (ast.Name, ast.Attribute)) or not isinstance(node.ctx, ast.Load):
        return None
    if isinstance(node, ast.Name):
        return imported.members.get(node.id)
    owner = _dotted_name(node.value)
    if owner is None or owner not in imported.modules:
        return None
    return ModuleUse(imported.modules[owner], node.attr)


def module_uses(scopes: Iterable[ast.AST], imported: ImportedNames) -> list[ModuleUse]:
    """Every imported module member read in the scopes, once each. Whether
    it is a function or constant of a project module is only known once
    every file is parsed."""
    found = (use for scope in scopes for node in ast.walk(scope) if (use := _module_use(node, imported)))
    return list(dict.fromkeys(found))


def newed_types(class_node: ast.ClassDef) -> list[str]:
    """Classes instantiated anywhere in the class body."""
    return [called for node in ast.walk(class_node) if (called := constructor_called(node))]
