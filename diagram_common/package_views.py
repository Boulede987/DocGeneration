"""Aggregate per-file diagrams into "general" views, each written in a base
variant (inheritance + composition) and a full variant (every relation):
  <ViewsDir>/<package>.puml  — one diagram per package, classes from other
                               project packages drawn as linked stubs
  <ViewsDir>/_overview.puml  — packages only, linked by cross-package usage
  <ViewsDir>/_project.puml   — every class of the project in one diagram

The package (a Java package or C# namespace) is the only grouping unit that
can be derived from source without guessing intent — there's no reliable
way to infer which packages form a logical "module" together, so each
package gets its own diagram and the overview shows how they reference
each other.
"""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .file_diagram import FileDiagram, relation_ends
from .puml import namespace_block, wrap_document, write_file

FULL_VIEWS_SUFFIX = "-Full"
OVERVIEW_NAME = "_overview"
PROJECT_NAME = "_project"

_DEFAULT_PACKAGE = "default_package"
_EXTERNAL_SKINPARAM = [
    "skinparam class {",
    "  BackgroundColor<<external>> #EAECEE",
    "  BorderColor<<external>> #839192",
    "}",
]

RelSelector = Callable[[FileDiagram], list[str]]


@dataclass(frozen=True)
class _ViewVariant:
    dir_suffix: str
    select_rels: RelSelector


_VARIANTS = (
    _ViewVariant("", FileDiagram.base_rels),
    _ViewVariant(FULL_VIEWS_SUFFIX, FileDiagram.full_rels),
)


@dataclass(frozen=True)
class _PackageIndex:
    files_by_package: dict[str | None, list[FileDiagram]]
    file_names: dict[str | None, str]

    def sorted_packages(self) -> list[str | None]:
        return sorted(self.files_by_package, key=_display_name)


def _display_name(package: str | None) -> str:
    return package if package else _DEFAULT_PACKAGE


def _alias(package: str | None) -> str:
    return re.sub(r"\W", "_", _display_name(package))


def _file_names_by_package(packages: set[str | None]) -> dict[str | None, str]:
    """Short, readable filename per package: the last path segment, unless
    two different packages share it — then fall back to the full path."""
    last_segment = {pkg: _display_name(pkg).split(".")[-1] for pkg in packages}
    segment_counts: dict[str, int] = {}
    for seg in last_segment.values():
        segment_counts[seg] = segment_counts.get(seg, 0) + 1
    return {
        pkg: seg if segment_counts[seg] == 1 else _display_name(pkg)
        for pkg, seg in last_segment.items()
    }


def _build_index(file_diagrams: list[FileDiagram]) -> _PackageIndex:
    files_by_package: dict[str | None, list[FileDiagram]] = {}
    for fd in file_diagrams:
        files_by_package.setdefault(fd.package, []).append(fd)
    return _PackageIndex(files_by_package, _file_names_by_package(set(files_by_package)))


def _declarations(fds: list[FileDiagram]) -> list[str]:
    return [line for fd in fds for line in fd.inner_lines]


def _qualified_rels(fds: list[FileDiagram], select_rels: RelSelector) -> list[str]:
    rels = [line for fd in fds for line in fd.qualify_rels(select_rels(fd))]
    return list(dict.fromkeys(rels))  # de-dup while keeping first-seen order


def _target_packages(fd: FileDiagram, rel_lines: list[str]) -> dict[str, str | None]:
    """Qualified name -> package, for each relation target."""
    targets = (relation_ends(line)[1] for line in rel_lines)
    return {fd.qualified_name(t): fd.name_packages.get(t) for t in targets}


def _external_targets(
    package: str | None,
    fds: list[FileDiagram],
    select_rels: RelSelector,
    index: _PackageIndex,
) -> dict[str, str]:
    """Qualified name -> package, for relation targets declared in another
    project package. A None package means 'unresolved', so such targets are
    never stubbed, even when the project has a default package."""
    targets: dict[str, str | None] = {}
    for fd in fds:
        targets.update(_target_packages(fd, select_rels(fd)))
    return {
        name: target_pkg
        for name, target_pkg in targets.items()
        if target_pkg is not None and target_pkg != package and target_pkg in index.files_by_package
    }


def _external_stub(qualified_name: str, file_name: str) -> list[str]:
    return [f"class {qualified_name} <<external>> [[{file_name}.svg]] {{", "}"]


def _build_package_diagram(
    package: str | None,
    select_rels: RelSelector,
    index: _PackageIndex,
    skinparam_lines: list[str],
) -> tuple[list[str], set[str]]:
    """Returns (puml_lines, referenced_packages) for one package's diagram."""
    fds = index.files_by_package[package]
    external = _external_targets(package, fds, select_rels, index)
    stubs = [
        line
        for name, target_pkg in sorted(external.items())
        for line in _external_stub(name, index.file_names[target_pkg])
    ]
    body = namespace_block(package, _declarations(fds)) + stubs + [""] + _qualified_rels(fds, select_rels)
    skinparam = skinparam_lines + [""] + _EXTERNAL_SKINPARAM
    return wrap_document(index.file_names[package], skinparam, body), set(external.values())


def _build_overview_diagram(
    index: _PackageIndex,
    package_refs: dict[str | None, set[str]],
    skinparam_lines: list[str],
) -> list[str]:
    body: list[str] = []
    for pkg in index.sorted_packages():
        body.append(f'package "{_display_name(pkg)}" as {_alias(pkg)} [[{index.file_names[pkg]}.svg]] {{')
        body.append("}")
    body.append("")
    for pkg in index.sorted_packages():
        body.extend(f"{_alias(pkg)} ..> {_alias(target)}" for target in sorted(package_refs[pkg]))
    return wrap_document(OVERVIEW_NAME, skinparam_lines, body)


def _build_project_diagram(
    index: _PackageIndex,
    select_rels: RelSelector,
    skinparam_lines: list[str],
) -> list[str]:
    body: list[str] = []
    for pkg in index.sorted_packages():
        body.extend(namespace_block(pkg, _declarations(index.files_by_package[pkg])))
    all_fds = [fd for pkg in index.sorted_packages() for fd in index.files_by_package[pkg]]
    body += [""] + _qualified_rels(all_fds, select_rels)
    return wrap_document(PROJECT_NAME, skinparam_lines, body)


def _write_views(
    index: _PackageIndex,
    variant: _ViewVariant,
    out_dir: Path,
    skinparam_lines: list[str],
) -> None:
    package_refs: dict[str | None, set[str]] = {}
    for pkg in index.sorted_packages():
        lines, package_refs[pkg] = _build_package_diagram(pkg, variant.select_rels, index, skinparam_lines)
        write_file(out_dir / f"{index.file_names[pkg]}.puml", lines)

    overview = _build_overview_diagram(index, package_refs, skinparam_lines)
    write_file(out_dir / f"{OVERVIEW_NAME}.puml", overview)
    project = _build_project_diagram(index, variant.select_rels, skinparam_lines)
    write_file(out_dir / f"{PROJECT_NAME}.puml", project)


def generate_package_views(
    file_diagrams: list[FileDiagram],
    out_base: Path,
    views_dir: str,
    skinparam_lines: list[str],
) -> int:
    """Write every view into out_base/<views_dir> (base) and
    out_base/<views_dir>-Full. Returns the number of packages."""
    index = _build_index(file_diagrams)
    for variant in _VARIANTS:
        _write_views(index, variant, out_base / f"{views_dir}{variant.dir_suffix}", skinparam_lines)
    return len(index.files_by_package)
