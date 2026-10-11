"""A Python class body -> attributes and member lines."""

import ast
from dataclasses import dataclass

from docgen.core.model import Member, MemberKind
from docgen.oo.vocabulary import TypeVocabulary

from .syntax import (
    DUNDER, FunctionNode, constructor_called, decorator_names, functions_of, simple_name, type_text,
    visibility_of, walk_own_scope,
)

CONSTRUCTOR = "__init__"
SELF = "self"
NO_RETURN = "None"
CLASS_VARIABLE = "ClassVar"
STATIC_METHOD = "staticmethod"
STATIC_DECORATORS = {STATIC_METHOD, "classmethod"}
ABSTRACT_DECORATOR = "abstractmethod"
PROPERTY_DECORATORS = {"property", "cached_property", "abstractproperty"}
ACCESSOR_DECORATORS = {"getter", "setter", "deleter"}
VARIADIC_PREFIX = "*"
KEYWORD_VARIADIC_PREFIX = "**"
BOUND_PARAMETERS = 1  # self or cls
TYPING_HELPERS = {"TypeVar", "NewType", "ParamSpec", "TypeVarTuple", "TypeAliasType"}
TYPE_ALIAS = "TypeAlias"
_KIND_ORDER = {MemberKind.FIELD: 0, MemberKind.PROPERTY: 1, MemberKind.METHOD: 2}


@dataclass(frozen=True)
class Attribute:
    """A class-level variable or an attribute set on self in __init__.
    type_text: the annotation, else what's assigned (a constructed class or
    an annotated __init__ parameter), else None (unknown)."""
    name: str
    type_text: str | None
    is_static: bool


def _class_level_attribute(statement: ast.stmt) -> Attribute | None:
    """Annotated names are instance fields (dataclass style) unless
    ClassVar; plain assignments are class (static) variables."""
    if isinstance(statement, ast.AnnAssign) and isinstance(statement.target, ast.Name):
        is_class_variable = simple_name(statement.annotation) == CLASS_VARIABLE
        return Attribute(statement.target.id, type_text(statement.annotation), is_class_variable)
    if isinstance(statement, ast.Assign) and len(statement.targets) == 1 and isinstance(statement.targets[0], ast.Name):
        return Attribute(statement.targets[0].id, constructor_called(statement.value), True)
    return None


def _annotated_parameters(function: FunctionNode) -> dict[str, str]:
    """Parameter name -> annotation text, for annotated parameters."""
    arguments = function.args
    return {
        parameter.arg: type_text(parameter.annotation)
        for parameter in arguments.posonlyargs + arguments.args + arguments.kwonlyargs
        if parameter.annotation is not None
    }


def _assigned_type(value: ast.expr | None, annotated_types: dict[str, str]) -> str | None:
    """'Foo' for self.x = Foo(...); the parameter's annotation for
    self.x = parameter; None otherwise."""
    if isinstance(value, ast.Name) and value.id in annotated_types:
        return annotated_types[value.id]
    return constructor_called(value)


def _self_attribute_name(target: ast.expr) -> str | None:
    is_on_self = isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name) and target.value.id == SELF
    return target.attr if is_on_self else None


def _targets_and_values(node: ast.Assign) -> list[tuple[ast.expr, ast.expr | None]]:
    """Each assigned target with the value it receives: 'a = b = v' gives
    both v; 'a, b = x, y' pairs them up (None when the value can't be
    split)."""
    pairs: list[tuple[ast.expr, ast.expr | None]] = []
    for target in node.targets:
        if not isinstance(target, (ast.Tuple, ast.List)):
            pairs.append((target, node.value))
            continue
        values = node.value.elts if isinstance(node.value, (ast.Tuple, ast.List)) else []
        split = len(values) == len(target.elts)
        pairs.extend((element, values[index] if split else None) for index, element in enumerate(target.elts))
    return pairs


def _self_attributes(node: ast.AST, annotated_types: dict[str, str]) -> list[Attribute]:
    """Attributes set on self by one statement; an annotation wins over
    what's assigned."""
    if isinstance(node, ast.AnnAssign) and (name := _self_attribute_name(node.target)):
        return [Attribute(name, type_text(node.annotation), False)]
    if not isinstance(node, ast.Assign):
        return []
    return [
        Attribute(name, _assigned_type(value, annotated_types), False)
        for target, value in _targets_and_values(node)
        if (name := _self_attribute_name(target))
    ]


def _constructor_attributes(class_node: ast.ClassDef) -> list[Attribute]:
    attributes: list[Attribute] = []
    for constructor in (function for function in functions_of(class_node) if function.name == CONSTRUCTOR):
        annotated_types = _annotated_parameters(constructor)
        for node in walk_own_scope(constructor):
            attributes.extend(_self_attributes(node, annotated_types))
    return attributes


def attributes_of(class_node: ast.ClassDef) -> list[Attribute]:
    """Class-level first, then __init__'s, each name once (first wins)."""
    candidates = [
        attribute for statement in class_node.body if (attribute := _class_level_attribute(statement))
    ] + _constructor_attributes(class_node)
    unique: dict[str, Attribute] = {}
    for attribute in candidates:
        unique.setdefault(attribute.name, attribute)
    return list(unique.values())


def _parameter_text(parameter: ast.arg, prefix: str = "") -> str:
    """The annotation, or the parameter's name when unannotated."""
    return prefix + (type_text(parameter.annotation) if parameter.annotation else parameter.arg)


def parameter_types(function: FunctionNode, is_method: bool) -> list[str]:
    """Signature in declaration order, variadics marked '*'/'**'. A
    method's bound first parameter (self/cls) is not part of it."""
    arguments = function.args
    positional = arguments.posonlyargs + arguments.args
    if is_method and STATIC_METHOD not in decorator_names(function):
        positional = positional[BOUND_PARAMETERS:]
    texts = [_parameter_text(parameter) for parameter in positional]
    if arguments.vararg:
        texts.append(_parameter_text(arguments.vararg, VARIADIC_PREFIX))
    texts.extend(_parameter_text(parameter) for parameter in arguments.kwonlyargs)
    if arguments.kwarg:
        texts.append(_parameter_text(arguments.kwarg, KEYWORD_VARIADIC_PREFIX))
    return texts


def return_type(function: FunctionNode) -> str | None:
    """None when unannotated or annotated '-> None'."""
    if function.returns is None:
        return None
    text = type_text(function.returns)
    return None if text == NO_RETURN else text


def _is_accessor(function: FunctionNode) -> bool:
    """@x.getter / @x.setter / @x.deleter: the property is listed once."""
    return any(
        isinstance(decorator, ast.Attribute) and decorator.attr in ACCESSOR_DECORATORS
        for decorator in function.decorator_list
    )


def _function_member(function: FunctionNode) -> Member:
    decorators = decorator_names(function)
    is_property = bool(decorators & PROPERTY_DECORATORS)
    return Member(
        kind=MemberKind.PROPERTY if is_property else MemberKind.METHOD,
        name=function.name,
        visibility=visibility_of(function.name),
        is_static=bool(decorators & STATIC_DECORATORS),
        is_abstract=ABSTRACT_DECORATOR in decorators,
        type=return_type(function),
        params=[] if is_property else parameter_types(function, is_method=True),
    )


def _attribute_member(attribute: Attribute, vocabulary: TypeVocabulary) -> Member:
    display_type = vocabulary.uml_type(attribute.type_text) if attribute.type_text else None
    return Member(
        kind=MemberKind.FIELD, name=attribute.name, visibility=visibility_of(attribute.name),
        is_static=attribute.is_static, is_abstract=False, type=display_type, params=[],
    )


def members_of(class_node: ast.ClassDef, vocabulary: TypeVocabulary) -> list[Member]:
    """Fields, then properties, then methods, each in source order;
    __init__ itself isn't shown (its attributes are)."""
    fields = [_attribute_member(attribute, vocabulary) for attribute in attributes_of(class_node)]
    functions = [
        _function_member(function)
        for function in functions_of(class_node)
        if function.name != CONSTRUCTOR and not _is_accessor(function)
    ]
    return sorted(fields + functions, key=lambda member: _KIND_ORDER[member.kind])


def module_functions(tree: ast.Module) -> list[FunctionNode]:
    return [statement for statement in tree.body if isinstance(statement, FunctionNode)]


def _is_typing_helper(value: ast.expr | None) -> bool:
    """T = TypeVar("T") and kin define types, not variables."""
    return isinstance(value, ast.Call) and simple_name(value.func) in TYPING_HELPERS


def _is_dunder(name: str) -> bool:
    return name.startswith(DUNDER) and name.endswith(DUNDER)


def _annotated_variable(statement: ast.AnnAssign) -> list[Attribute]:
    """A bare annotation ('pending: int') binds nothing; 'X: TypeAlias = ...'
    names a type."""
    is_binding = statement.value is not None and isinstance(statement.target, ast.Name)
    if not is_binding or simple_name(statement.annotation) == TYPE_ALIAS:
        return []
    return [Attribute(statement.target.id, type_text(statement.annotation), is_static=True)]


def _assigned_variables(statement: ast.Assign) -> list[Attribute]:
    """'A = B = 1' and 'C, D = 2, 3' bind every name."""
    if _is_typing_helper(statement.value):
        return []
    return [
        Attribute(target.id, constructor_called(value), is_static=True)
        for target, value in _targets_and_values(statement)
        if isinstance(target, ast.Name)
    ]


def _variables_bound_by(statement: ast.stmt) -> list[Attribute]:
    if isinstance(statement, ast.AnnAssign):
        return _annotated_variable(statement)
    if isinstance(statement, ast.Assign):
        return _assigned_variables(statement)
    return []


def module_variables(tree: ast.Module) -> list[Attribute]:
    """Every name the module's top-level statements bind: constants and
    module state alike (_cache, logger). Bindings under if/try depend on the
    environment (TYPE_CHECKING, platform), so they're left out; dunders
    (__all__, __version__) are metadata."""
    return [
        variable
        for statement in tree.body
        for variable in _variables_bound_by(statement)
        if not _is_dunder(variable.name)
    ]


def _module_function_member(function: FunctionNode) -> Member:
    return Member(
        kind=MemberKind.METHOD, name=function.name, visibility=visibility_of(function.name),
        is_static=True, is_abstract=False, type=return_type(function),
        params=parameter_types(function, is_method=False),
    )


def module_members(tree: ast.Module, vocabulary: TypeVocabulary) -> list[Member]:
    """Module variables as static fields, then free functions as static
    methods: a module behaves like a class with only static members."""
    variables = [_attribute_member(variable, vocabulary) for variable in module_variables(tree)]
    return variables + [_module_function_member(function) for function in module_functions(tree)]


def has_abstract_method(class_node: ast.ClassDef) -> bool:
    return any(ABSTRACT_DECORATOR in decorator_names(function) for function in functions_of(class_node))
