"""The type texts a Python class or module holds (attributes) or mentions
(signatures, function bodies, module-level assignments)."""

import ast
from typing import Iterable

from docgen.core.model import Visibility
from docgen.oo.facts import FieldUsage

from .members import CONSTRUCTOR, attributes_of, module_functions, parameter_types, return_type
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
    assignments = [statement for statement in tree.body if isinstance(statement, (ast.Assign, ast.AnnAssign))]
    return _mentioned_in([*module_functions(tree), *assignments])


def newed_types(class_node: ast.ClassDef) -> list[str]:
    """Classes instantiated anywhere in the class body."""
    return [called for node in ast.walk(class_node) if (called := constructor_called(node))]
