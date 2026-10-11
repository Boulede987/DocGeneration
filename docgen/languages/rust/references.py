"""What a piece of Rust code mentions: type names (in signatures and
bodies) and other modules' functions and constants. Kept as written;
resolved at link time, when the whole crate is known.

Rust's naming conventions tell paths apart: a capitalized segment is a type
(Foo, T, IO), SCREAMING_CASE at the end of a path is a constant, anything
else lowercase is a module or a function."""

from typing import TYPE_CHECKING

from .facts import ItemUse, UseBinding
from .modules import CRATE, PARENT_MODULE, SELF_MODULE
from .syntax import NAMED_TYPE_NODES, PATH_SEPARATOR, SELF_TYPE, field, node_text, walk, without_type_arguments

if TYPE_CHECKING:
    from tree_sitter import Node

PATH_EXPRESSION = "scoped_identifier"
CALL_EXPRESSION = "call_expression"
IDENTIFIER = "identifier"
PATTERN_FIELD = "pattern"
CLOSURE_PARAMETERS = "closure_parameters"
_MODULE_KEYWORDS = frozenset({CRATE, SELF_MODULE, PARENT_MODULE})


def _is_type_segment(segment: str) -> bool:
    return segment[:1].isupper() and segment != SELF_TYPE


def _is_constant(name: str) -> bool:
    return len(name) > 1 and name.isupper()


def _path_segments(node: "Node") -> list[str]:
    return without_type_arguments(node_text(node)).split(PATH_SEPARATOR)


def _type_in_path(segments: list[str]) -> str | None:
    """The path up to its first type: 'Currency::Eur' -> 'Currency',
    'a::B::new' -> 'a::B', 'models::Point' -> 'models::Point'. A
    SCREAMING_CASE tail is a constant, not a type."""
    for index, segment in enumerate(segments):
        if segment == SELF_TYPE:
            return None
        is_tail = index == len(segments) - 1
        if _is_type_segment(segment) and not (is_tail and _is_constant(segment)):
            return PATH_SEPARATOR.join(segments[:index + 1])
    return None


def type_names(node: "Node | None") -> list[str]:
    """Named types in a type or a block: annotations, struct literals,
    turbofish arguments, paths through a type."""
    if node is None:
        return []
    names: list[str] = []
    for current in walk(node, stop_at=NAMED_TYPE_NODES):
        if current.type in NAMED_TYPE_NODES:
            name = without_type_arguments(node_text(current))
            if name != SELF_TYPE:
                names.append(name)
        elif current.type == PATH_EXPRESSION and (type_path := _type_in_path(_path_segments(current))):
            names.append(type_path)
    return list(dict.fromkeys(names))


def _pattern_names(node: "Node") -> set[str]:
    """Names bound inside the code (parameters, let, for, match, closures):
    a local named like an imported function is not that function."""
    bound: set[str] = set()
    for current in walk(node):
        pattern = field(current, PATTERN_FIELD) if current.type != CLOSURE_PARAMETERS else current
        if pattern is not None:
            bound |= {node_text(name) for name in walk(pattern) if name.type == IDENTIFIER}
    return bound


def _module_path_use(segments: list[str]) -> ItemUse | None:
    """pricing::total, crate::util::RATE: a module path, then a function or
    constant. A path through a type is a type mention instead."""
    *prefix, name = segments
    if not prefix or any(_is_type_segment(segment) for segment in prefix if segment not in _MODULE_KEYWORDS):
        return None
    if _is_type_segment(name) and not _is_constant(name):
        return None
    return ItemUse(PATH_SEPARATOR.join(prefix), name)


def item_uses(node: "Node | None", uses: list[UseBinding]) -> list[ItemUse]:
    """Functions and constants used through a module path, or bare: bare
    names count when a use declaration binds them or when they are called
    (a glob may bring them in), unless a local binding shadows them."""
    if node is None:
        return []
    imported = {binding.local_name for binding in uses if not binding.is_glob}
    local = _pattern_names(node)
    called = {
        node_text(function)
        for current in walk(node)
        if current.type == CALL_EXPRESSION and (function := field(current, "function")) is not None
        and function.type == IDENTIFIER
    }
    found: list[ItemUse] = []
    for current in walk(node, stop_at=frozenset({PATH_EXPRESSION})):
        if current.type == IDENTIFIER:
            name = node_text(current)
            if (name in imported or name in called) and name not in local:
                found.append(ItemUse(None, name))
        elif current.type == PATH_EXPRESSION and (use := _module_path_use(_path_segments(current))):
            found.append(use)
    return list(dict.fromkeys(found))
