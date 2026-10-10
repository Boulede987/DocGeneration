"""Which package a referenced simple name belongs to. A name that can't be
placed with confidence resolves to None and is drawn outside any package
rather than guessed into one."""

from typing import Callable

from .model import ParsedFile

EnclosingPackages = Callable[[str | None], list[str | None]]


class ProjectIndex:
    """Every project type's simple name -> the package(s) declaring it. A
    name maps to several packages when unrelated packages reuse it."""

    def __init__(self, parsed_files: list[ParsedFile]):
        self._packages_by_name: dict[str, set[str | None]] = {}
        for parsed in parsed_files:
            for declaration in parsed.declarations:
                self._packages_by_name.setdefault(declaration.bare_name, set()).add(parsed.package)

    def known_types(self) -> set[str]:
        return set(self._packages_by_name)

    def packages_of(self, name: str) -> set[str | None]:
        return self._packages_by_name.get(name, set())


def resolve_package(
    name: str,
    parsed: ParsedFile,
    index: ProjectIndex,
    enclosing_packages: EnclosingPackages,
) -> str | None:
    """First match wins: declared in this file; imported by name; declared
    in a package visible from this file without import (closest first);
    declared in exactly one wholly-imported package; declared in exactly one
    project package."""
    if name in {declaration.bare_name for declaration in parsed.declarations}:
        return parsed.package
    if name in parsed.hints.type_imports:
        return parsed.hints.type_imports[name]
    candidates = index.packages_of(name)
    for package in enclosing_packages(parsed.package):
        if package in candidates:
            return package
    imported = candidates & parsed.hints.namespace_imports
    if len(imported) == 1:
        return next(iter(imported))
    if len(candidates) == 1:
        return next(iter(candidates))
    return None
