"""Where a Python module sits (its package, from its folder) and which
packages its imports make visible."""

import ast
from pathlib import Path

from docgen.core.model import ResolutionHints

PACKAGE_SEPARATOR = "."


def package_of(relative_path: Path) -> str | None:
    """'shop/model/product.py' -> 'shop.model'; a root-level module has no
    package."""
    folders = relative_path.parent.parts
    return PACKAGE_SEPARATOR.join(folders) if folders else None


def _absolute_module(node: ast.ImportFrom, package: str | None) -> str | None:
    """Resolve 'from ..model import x' against the importing file's package:
    level 1 is the package itself, each further level one folder up. None
    when the import climbs above the top-level package (or comes from a
    root-level module): Python refuses those, so they point nowhere."""
    if node.level == 0:
        return node.module or None
    anchor = package.split(PACKAGE_SEPARATOR) if package else []
    levels_up = node.level - 1
    if levels_up >= len(anchor):
        return None
    named = node.module.split(PACKAGE_SEPARATOR) if node.module else []
    return PACKAGE_SEPARATOR.join(anchor[:len(anchor) - levels_up] + named)


def _module_and_parent(module: str) -> set[str]:
    """Import syntax can't tell a module file from a package: a dotted path
    may name either, so both it and its parent are candidates."""
    parent = module.rpartition(PACKAGE_SEPARATOR)[0]
    return {path for path in (module, parent) if path}


def _imported_paths(node: ast.AST, package: str | None) -> set[str]:
    if isinstance(node, ast.ImportFrom):
        module = _absolute_module(node, package)
        return _module_and_parent(module) if module else set()
    if isinstance(node, ast.Import):
        return {path for alias in node.names for path in _module_and_parent(alias.name)}
    return set()


def import_hints(tree: ast.Module, package: str | None) -> ResolutionHints:
    """Imports anywhere in the module, including inside functions and
    conditional blocks."""
    imported = {path for node in ast.walk(tree) for path in _imported_paths(node, package)}
    return ResolutionHints(namespace_imports=imported)
