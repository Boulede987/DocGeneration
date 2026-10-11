"""Where a Rust file sits in its crate's module tree, and what its use
declarations bind."""

from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING

from .facts import UseBinding
from .syntax import field, is_test_only, named_children, node_text, walk

if TYPE_CHECKING:
    from tree_sitter import Node

MODULE_SEPARATOR = "."
CRATE_ROOT_STEMS = frozenset({"lib", "main"})
MODULE_DIRECTORY_STEM = "mod"
CRATE = "crate"
SELF_MODULE = "self"
PARENT_MODULE = "super"
UNNAMED_IMPORT = "_"
GLOB_LOCAL_NAME = ""
INLINE_MODULE = "mod_item"
USE_DECLARATION = "use_declaration"
_PATH_NODES = frozenset({"identifier", "scoped_identifier", CRATE, SELF_MODULE, PARENT_MODULE})


def module_path_of(relative_path: Path) -> str | None:
    """'model/product.rs' and 'model/product/mod.rs' -> 'model.product';
    lib.rs or main.rs at the source root is the crate root (None)."""
    parts = list(relative_path.parent.parts)
    stem = relative_path.stem
    if not parts and stem in CRATE_ROOT_STEMS:
        return None
    if stem != MODULE_DIRECTORY_STEM:
        parts.append(stem)
    return MODULE_SEPARATOR.join(parts) if parts else None


def path_segments(node: "Node") -> list[str]:
    """'crate::a::B' -> ['crate', 'a', 'B']."""
    if node.type == "scoped_identifier":
        prefix = field(node, "path")
        name = field(node, "name")
        return (path_segments(prefix) if prefix is not None else []) + ([node_text(name)] if name is not None else [])
    return [node_text(node)]


def _imported_path(segments: list[str]) -> list[str]:
    """'a::b::self' imports the module a::b itself."""
    is_module_itself = len(segments) > 1 and segments[-1] == SELF_MODULE
    return segments[:-1] if is_module_itself else segments


def _bindings(node: "Node", prefix: list[str]) -> list[UseBinding]:
    """One use tree: a path, 'path as alias', 'path::*', or 'path::{...}'.
    'as _' imports a trait for its methods only: it binds no name."""
    if node.type in _PATH_NODES:
        path = _imported_path(prefix + path_segments(node))
        return [UseBinding(path[-1], tuple(path), is_glob=False)]
    if node.type == "use_as_clause":
        path_node, alias = field(node, "path"), field(node, "alias")
        if path_node is None or alias is None or node_text(alias) == UNNAMED_IMPORT:
            return []
        return [UseBinding(node_text(alias), tuple(_imported_path(prefix + path_segments(path_node))), is_glob=False)]
    if node.type == "use_wildcard":
        module = named_children(node)
        return [UseBinding(GLOB_LOCAL_NAME, tuple(prefix + (path_segments(module[0]) if module else [])), is_glob=True)]
    if node.type == "scoped_use_list":
        path_node = field(node, "path")
        nested_prefix = prefix + (path_segments(path_node) if path_node is not None else [])
        return [binding for child in named_children(field(node, "list")) for binding in _bindings(child, nested_prefix)]
    if node.type == "use_list":
        return [binding for child in named_children(node) for binding in _bindings(child, prefix)]
    return []


def use_bindings(container: "Node", scope: tuple[str, ...] = ()) -> list[UseBinding]:
    """Every use declaration of the file, in source order: at file level,
    in function bodies, and in inline modules (scoped to them). Test-only
    code is skipped: its imports are not the file's."""
    bindings: list[UseBinding] = []
    for child in named_children(container):
        if is_test_only(child):
            continue
        body = field(child, "body") if child.type == INLINE_MODULE else None
        if body is not None:
            bindings += use_bindings(body, scope + (node_text(field(child, "name")),))
            continue
        for declaration in (node for node in walk(child) if node.type == USE_DECLARATION):
            if (argument := field(declaration, "argument")) is not None:
                bindings += [replace(binding, scope=scope) for binding in _bindings(argument, [])]
    return bindings
