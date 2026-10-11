"""Where a Python module sits (its package, from its folder), which
packages its imports make visible, and which other modules' names it
imports."""

import ast
from dataclasses import dataclass, field
from pathlib import Path

from docgen.core.model import ResolutionHints

PACKAGE_SEPARATOR = "."
PACKAGE_MODULE_STEM = "__init__"
STAR_IMPORT = "*"


@dataclass(frozen=True)
class ModuleUse:
    """A name imported from another module (one of its top-level names, or
    a submodule): module_path is the dotted path Python imports that module
    by."""
    module_path: str
    name: str


@dataclass
class ImportedNames:
    """What a file's imports bind. members: local name -> the module member
    it stands for. modules: local dotted name -> module path. 'from pkg
    import x' fills both: x may be a member of pkg or the module pkg.x, the
    syntax can't tell, and only one of them can exist in the project."""
    members: dict[str, ModuleUse] = field(default_factory=dict)
    modules: dict[str, str] = field(default_factory=dict)


def package_of(relative_path: Path) -> str | None:
    """'shop/model/product.py' -> 'shop.model'; a root-level module has no
    package."""
    folders = relative_path.parent.parts
    return PACKAGE_SEPARATOR.join(folders) if folders else None


def module_path_of(relative_path: Path) -> str | None:
    """The dotted path Python imports the file by: 'shop/util/pricing.py' ->
    'shop.util.pricing', 'shop/__init__.py' -> 'shop'. None for a
    root-level __init__.py, which no import can name."""
    parts = list(relative_path.parent.parts)
    if relative_path.stem != PACKAGE_MODULE_STEM:
        parts.append(relative_path.stem)
    return PACKAGE_SEPARATOR.join(parts) if parts else None


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


def _prefixes(dotted: str) -> list[str]:
    """'a.b.c' -> ['a', 'a.b', 'a.b.c']."""
    parts = dotted.split(PACKAGE_SEPARATOR)
    return [PACKAGE_SEPARATOR.join(parts[:length]) for length in range(1, len(parts) + 1)]


def _bind_import(node: ast.Import, imported: ImportedNames) -> None:
    """'import a.b' binds a, through which a and a.b are reachable;
    'import a.b as y' binds y to a.b."""
    for alias in node.names:
        if alias.asname:
            imported.modules[alias.asname] = alias.name
            continue
        for prefix in _prefixes(alias.name):
            imported.modules[prefix] = prefix


def _bind_import_from(node: ast.ImportFrom, package: str | None, imported: ImportedNames) -> None:
    module = _absolute_module(node, package)
    if module is None:
        return
    for alias in node.names:
        if alias.name == STAR_IMPORT:
            continue  # binds names only the imported module's text knows
        local_name = alias.asname or alias.name
        imported.members[local_name] = ModuleUse(module, alias.name)
        imported.modules[local_name] = PACKAGE_SEPARATOR.join((module, alias.name))


def _imports_in_source_order(tree: ast.Module) -> list[ast.Import | ast.ImportFrom]:
    """ast.walk goes breadth-first: an import nested in a function would
    come after a later top-level one."""
    imports = [node for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom))]
    return sorted(imports, key=lambda node: (node.lineno, node.col_offset))


def imported_names(tree: ast.Module, package: str | None) -> ImportedNames:
    """Imports anywhere in the module, including inside functions. A name
    bound twice keeps its last binding in the source: scopes are not told
    apart."""
    imported = ImportedNames()
    for node in _imports_in_source_order(tree):
        if isinstance(node, ast.Import):
            _bind_import(node, imported)
        elif isinstance(node, ast.ImportFrom):
            _bind_import_from(node, package, imported)
    return imported
