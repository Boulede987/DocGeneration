"""Reading Rust syntax trees with tree-sitter: parsing, node text, display
text without lifetimes, and the node kinds the Rust modules share.
tree-sitter is imported on first use, so the other languages run without
it installed."""

import re
from collections.abc import Iterator
from functools import cache
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tree_sitter import Node, Parser

SOURCE_ENCODING = "utf-8"
INSTALL_HINT = "Rust support needs tree-sitter: python -m pip install -r requirements.txt"
PATH_SEPARATOR = "::"
TYPE_ARGUMENTS = re.compile(r"<[^<>]*>")
ERROR_NODE = "ERROR"
NAMED_TYPE_NODES = frozenset({"type_identifier", "scoped_type_identifier"})
SELF_TYPE = "Self"
ATTRIBUTE = "attribute_item"
COMMENTS = frozenset({"line_comment", "block_comment"})
# #[cfg(test)], #[cfg(all(test, ...))]: compiled for tests only; not(test) is the opposite.
_TEST_ONLY = re.compile(r"^#\[cfg\((?!.*\bnot\s*\(\s*test\b).*\btest\b.*\)\]$")
_FIRST_LINE_NUMBER = 1
# PlantUML reads a quote as the start of a comment, and lifetimes say
# nothing about structure: 'a and 'static are dropped from displayed types.
_LIFETIME_BINDER = re.compile(r"\bfor\s*<\s*'\w+(\s*,\s*'\w+)*\s*>\s*")
_LIFETIME_BOUND = re.compile(r"\s*\+\s*'\w+")
_LIFETIME_ARGUMENT = re.compile(r"'\w+\s*,\s*")
_LIFETIME = re.compile(r"'\w+\s*")
_EMPTY_ARGUMENTS = re.compile(r"<\s*>")
_SPACES = re.compile(r"\s+")


class RustSyntaxError(ValueError):
    """The file needed repairs to parse: it is reported, not drawn."""


class RustSupportMissing(ImportError):
    """tree-sitter isn't installed: raised for each Rust file, with the
    install command."""


@cache
def _parser() -> "Parser":
    try:
        import tree_sitter
        import tree_sitter_rust
    except ImportError as error:
        raise RustSupportMissing(INSTALL_HINT) from error
    return tree_sitter.Parser(tree_sitter.Language(tree_sitter_rust.language()))


def _first_error(root: "Node") -> "Node | None":
    """Depth-first, without recursion: deeply nested code must not hit
    Python's recursion limit."""
    pending = [root]
    while pending:
        node = pending.pop()
        if node.type == ERROR_NODE or node.is_missing:
            return node
        pending.extend(reversed([child for child in node.children if child.has_error or child.is_missing]))
    return None


def parse_tree(text: str) -> "Node":
    """The file's root node. tree-sitter recovers from errors; a file it
    had to repair is refused, so a wrong diagram is never drawn from it."""
    root = _parser().parse(text.encode(SOURCE_ENCODING)).root_node
    if root.has_error:
        error = _first_error(root)
        location = error if error is not None else root
        raise RustSyntaxError(f"line {location.start_point.row + _FIRST_LINE_NUMBER}: cannot parse")
    return root


def is_test_only(item: "Node") -> bool:
    """Attributes come as siblings right before the item, comments may sit
    between them."""
    sibling = item.prev_named_sibling
    while sibling is not None and (sibling.type == ATTRIBUTE or sibling.type in COMMENTS):
        if sibling.type == ATTRIBUTE and _TEST_ONLY.match(" ".join(node_text(sibling).split())):
            return True
        sibling = sibling.prev_named_sibling
    return False


def node_text(node: "Node") -> str:
    return (node.text or b"").decode(SOURCE_ENCODING)


def display_text(node: "Node") -> str:
    """A type's source text on one line, without lifetimes: '&'a Product'
    -> '&Product'. Only ever given type nodes (no literals)."""
    text = _LIFETIME_BINDER.sub("", node_text(node))
    text = _LIFETIME_BOUND.sub("", text)
    text = _LIFETIME.sub("", _LIFETIME_ARGUMENT.sub("", text))
    return _SPACES.sub(" ", _EMPTY_ARGUMENTS.sub("", text)).strip()


def without_type_arguments(path: str) -> str:
    """'Vec::<Foo>::new' -> 'Vec::new', 'Wrapper<T>' -> 'Wrapper'."""
    previous = None
    while previous != path:
        previous, path = path, TYPE_ARGUMENTS.sub("", path)
    return path.replace(PATH_SEPARATOR + PATH_SEPARATOR, PATH_SEPARATOR).strip(":")


def field(node: "Node", name: str) -> "Node | None":
    return node.child_by_field_name(name)


def named_children(node: "Node | None", kind: str | None = None) -> list["Node"]:
    if node is None:
        return []
    return [child for child in node.named_children if kind is None or child.type == kind]


def walk(node: "Node", stop_at: frozenset[str] = frozenset()) -> Iterator["Node"]:
    """Every node under the given one (included), in source order, without
    descending into nodes of the stop_at kinds (those are yielded, their
    children are not)."""
    pending = [node]
    while pending:
        current = pending.pop()
        yield current
        if current.type not in stop_at:
            pending.extend(reversed(current.named_children))
