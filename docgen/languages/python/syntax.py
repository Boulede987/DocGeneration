"""Reading Python syntax trees: annotation text, simple names, decorators,
scopes, and naming-convention visibility."""

import ast
import copy
from typing import Iterator

from docgen.core.model import Visibility

DUNDER = "__"
PROTECTED_PREFIX = "_"
LITERAL = "Literal"
ANNOTATED = "Annotated"
FunctionNode = ast.FunctionDef | ast.AsyncFunctionDef
_NESTED_SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)


def _parsed_type_expression(text: str) -> ast.expr | None:
    try:
        return ast.parse(text, mode="eval").body
    except SyntaxError:
        return None


class _UnquoteForwardReferences(ast.NodeTransformer):
    """A quoted type ('Tag', "list[Node]") names the same type as the
    unquoted expression. Strings that are values, not types — Literal's
    arguments and Annotated's metadata — keep their quotes."""

    def visit_Constant(self, node: ast.Constant) -> ast.AST:
        if not isinstance(node.value, str):
            return node
        parsed = _parsed_type_expression(node.value)
        return self.visit(parsed) if parsed is not None else node

    def visit_Subscript(self, node: ast.Subscript) -> ast.AST:
        name = simple_name(node.value)
        if name == LITERAL:
            return node
        if name == ANNOTATED and isinstance(node.slice, ast.Tuple) and node.slice.elts:
            node.slice.elts[0] = self.visit(node.slice.elts[0])
            return node
        return self.generic_visit(node)


def type_text(annotation: ast.expr) -> str:
    """The annotation as source text. Works on a copy: NodeTransformer edits
    in place, and the tree is read again afterwards."""
    return ast.unparse(_UnquoteForwardReferences().visit(copy.deepcopy(annotation)))


def simple_name(node: ast.expr) -> str | None:
    """'Foo' for Foo, a.b.Foo and Foo[T]; None for anything else."""
    if isinstance(node, ast.Subscript):
        return simple_name(node.value)
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Name):
        return node.id
    return None


def decorator_names(node: FunctionNode | ast.ClassDef) -> set[str]:
    """'property', 'abstractmethod', 'dataclass' for @x, @mod.x and @x(...)."""
    names: set[str] = set()
    for decorator in node.decorator_list:
        target = decorator.func if isinstance(decorator, ast.Call) else decorator
        if (name := simple_name(target)) is not None:
            names.add(name)
    return names


def visibility_of(name: str) -> Visibility:
    """__x private, _x protected, __dunder__ and anything else public."""
    is_dunder = name.startswith(DUNDER) and name.endswith(DUNDER)
    if is_dunder:
        return Visibility.PUBLIC
    if name.startswith(DUNDER):
        return Visibility.PRIVATE
    if name.startswith(PROTECTED_PREFIX):
        return Visibility.PROTECTED
    return Visibility.PUBLIC


def functions_of(class_node: ast.ClassDef) -> Iterator[FunctionNode]:
    return (statement for statement in class_node.body if isinstance(statement, FunctionNode))


def walk_own_scope(function: FunctionNode) -> Iterator[ast.AST]:
    """Every node of the function's body, without entering nested
    functions, classes or lambdas: their 'self' is not this one."""
    pending: list[ast.AST] = list(function.body)
    while pending:
        node = pending.pop(0)
        yield node
        if not isinstance(node, _NESTED_SCOPES):
            pending.extend(ast.iter_child_nodes(node))


def looks_like_class_name(name: str) -> bool:
    """PEP 8 capitalizes class names and nothing else common, so a
    capitalized callee or receiver is taken to be a class."""
    return name[:1].isupper()


def constructor_called(value: ast.AST | None) -> str | None:
    """'Foo' for 'Foo(...)' or 'mod.Foo(...)'. Capitalization is the only
    evidence, so a capitalized factory ('Config.Load()') reads as a class
    too."""
    if not isinstance(value, ast.Call):
        return None
    name = simple_name(value.func)
    return name if name and looks_like_class_name(name) else None
