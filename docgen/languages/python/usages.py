"""The type texts a Python class holds (attributes) or mentions (signatures,
method bodies)."""

import ast

from docgen.core.model import FieldUsage, Visibility

from .members import CONSTRUCTOR, attributes_of, parameter_types, return_type
from .syntax import constructor_called, functions_of, looks_like_class_name, type_text, visibility_of


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


def signature_types(class_node: ast.ClassDef) -> list[str]:
    """Parameter and return types of every method but __init__ (its
    parameters are what the attributes hold, not uses)."""
    types: list[str] = []
    for function in functions_of(class_node):
        if function.name == CONSTRUCTOR:
            continue
        types.extend(parameter_types(function))
        if (returned := return_type(function)) is not None:
            types.append(returned)
    return types


def _mentioned_type(node: ast.AST) -> str | None:
    """Without type inference, a body only reveals a type where it names
    one: a constructor call Foo(...), class access Foo.x, or a local
    annotation."""
    if called := constructor_called(node):
        return called
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and looks_like_class_name(node.value.id):
        return node.value.id
    if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        return type_text(node.annotation)
    return None


def body_types(class_node: ast.ClassDef) -> list[str]:
    """Every node of every method, nested calls and inner functions
    included: what they use, the class depends on."""
    return [
        mentioned
        for function in functions_of(class_node)
        for node in ast.walk(function)
        if (mentioned := _mentioned_type(node))
    ]


def newed_types(class_node: ast.ClassDef) -> list[str]:
    """Classes instantiated anywhere in the class body."""
    return [called for node in ast.walk(class_node) if (called := constructor_called(node))]
