"""Aggregate per-file diagrams into "general" views, each written in a base
variant (inheritance + composition) and a full variant (every relation):
  <ViewsDir>/<package>.puml  — one diagram per package, classes from other
                               project packages drawn as linked stubs
  <ViewsDir>/_overview.puml  — packages only, linked by cross-package usage
  <ViewsDir>/_project.puml   — every class of the project in one diagram

The grouping unit is the package: the only one derivable from source.
"""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .file_diagram import PUML_SUFFIX, FileDiagram
from .puml import namespace_block, wrap_document, write_file
from .relations import DEPENDS, Relation
from .style import StereotypeStyle

FULL_VIEWS_SUFFIX = "-Full"
OVERVIEW_NAME = "_overview"
PROJECT_NAME = "_project"

_DEFAULT_PACKAGE = "default_package"
_PACKAGE_SEPARATOR = "."
_SVG_SUFFIX = ".svg"
_EXTERNAL_STYLE = StereotypeStyle("external", "#EAECEE", "#839192")
_EXTERNAL_STEREOTYPE = f"<<{_EXTERNAL_STYLE.stereotype}>>"

RelationSelector = Callable[[FileDiagram], list[Relation]]


@dataclass(frozen=True)
class _ViewVariant:
    dir_suffix: str
    select_relations: RelationSelector


_VARIANTS = (
    _ViewVariant("", FileDiagram.base_relations),
    _ViewVariant(FULL_VIEWS_SUFFIX, FileDiagram.full_relations),
)


@dataclass(frozen=True)
class _PackageIndex:
    files_by_package: dict[str | None, list[FileDiagram]]
    file_names: dict[str | None, str]

    def sorted_packages(self) -> list[str | None]:
        return sorted(self.files_by_package, key=_display_name)

    def link(self, package: str | None) -> str:
        return f"[[{self.file_names[package]}{_SVG_SUFFIX}]]"


def _display_name(package: str | None) -> str:
    return package if package else _DEFAULT_PACKAGE


def _alias(package: str | None) -> str:
    return re.sub(r"\W", "_", _display_name(package))


def _file_names_by_package(packages: set[str | None]) -> dict[str | None, str]:
    """Short, readable filename per package: the last path segment, unless
    two different packages share it — then fall back to the full path."""
    last_segment = {package: _display_name(package).split(_PACKAGE_SEPARATOR)[-1] for package in packages}
    segment_counts: dict[str, int] = {}
    for segment in last_segment.values():
        segment_counts[segment] = segment_counts.get(segment, 0) + 1
    return {
        package: segment if segment_counts[segment] == 1 else _display_name(package)
        for package, segment in last_segment.items()
    }


def _build_index(file_diagrams: list[FileDiagram]) -> _PackageIndex:
    files_by_package: dict[str | None, list[FileDiagram]] = {}
    for file_diagram in file_diagrams:
        files_by_package.setdefault(file_diagram.package, []).append(file_diagram)
    return _PackageIndex(files_by_package, _file_names_by_package(set(files_by_package)))


def _declarations(file_diagrams: list[FileDiagram]) -> list[str]:
    return [line for file_diagram in file_diagrams for line in file_diagram.inner_lines]


def _qualified_relation_lines(file_diagrams: list[FileDiagram], select_relations: RelationSelector) -> list[str]:
    """Each line once, at its first occurrence: the same relation can come
    from several files, and output order must not depend on set ordering."""
    lines = [
        line
        for file_diagram in file_diagrams
        for line in file_diagram.render_relations(select_relations(file_diagram))
    ]
    return list(dict.fromkeys(lines))


def _target_packages(file_diagram: FileDiagram, relations: list[Relation]) -> dict[str, str | None]:
    """Qualified name -> package, for each relation target."""
    return {
        file_diagram.qualified_target(relation): file_diagram.target_package(relation)
        for relation in relations
    }


def _external_targets(
    package: str | None,
    file_diagrams: list[FileDiagram],
    select_relations: RelationSelector,
    index: _PackageIndex,
) -> dict[str, str]:
    """Qualified name -> package, for relation targets declared in another
    project package. A None package means 'unresolved', so such targets are
    never stubbed, even when the project has a default package."""
    targets: dict[str, str | None] = {}
    for file_diagram in file_diagrams:
        targets.update(_target_packages(file_diagram, select_relations(file_diagram)))
    return {
        name: target_package
        for name, target_package in targets.items()
        if target_package is not None and target_package != package and target_package in index.files_by_package
    }


def _external_stub(qualified_name: str, link: str) -> list[str]:
    return [f"class {qualified_name} {_EXTERNAL_STEREOTYPE} {link} {{", "}"]


def _build_package_diagram(
    package: str | None,
    select_relations: RelationSelector,
    index: _PackageIndex,
    skinparam_lines: list[str],
) -> tuple[list[str], set[str]]:
    """Returns (puml_lines, referenced_packages) for one package's diagram."""
    file_diagrams = index.files_by_package[package]
    external = _external_targets(package, file_diagrams, select_relations, index)
    stubs = [
        line
        for name, target_package in sorted(external.items())
        for line in _external_stub(name, index.link(target_package))
    ]
    body = (
        namespace_block(package, _declarations(file_diagrams))
        + stubs
        + [""]
        + _qualified_relation_lines(file_diagrams, select_relations)
    )
    skinparam = skinparam_lines + [""] + _EXTERNAL_STYLE.lines()
    return wrap_document(index.file_names[package], skinparam, body), set(external.values())


def _build_overview_diagram(
    index: _PackageIndex,
    package_references: dict[str | None, set[str]],
    skinparam_lines: list[str],
) -> list[str]:
    body: list[str] = []
    for package in index.sorted_packages():
        body.append(f'package "{_display_name(package)}" as {_alias(package)} {index.link(package)} {{')
        body.append("}")
    body.append("")
    for package in index.sorted_packages():
        body.extend(
            f"{_alias(package)} {DEPENDS} {_alias(target)}" for target in sorted(package_references[package])
        )
    return wrap_document(OVERVIEW_NAME, skinparam_lines, body)


def _build_project_diagram(
    index: _PackageIndex,
    select_relations: RelationSelector,
    skinparam_lines: list[str],
) -> list[str]:
    body: list[str] = []
    for package in index.sorted_packages():
        body.extend(namespace_block(package, _declarations(index.files_by_package[package])))
    all_file_diagrams = [
        file_diagram for package in index.sorted_packages() for file_diagram in index.files_by_package[package]
    ]
    body += [""] + _qualified_relation_lines(all_file_diagrams, select_relations)
    return wrap_document(PROJECT_NAME, skinparam_lines, body)


def _write_views(
    index: _PackageIndex,
    variant: _ViewVariant,
    views_path: Path,
    skinparam_lines: list[str],
) -> None:
    package_references: dict[str | None, set[str]] = {}
    for package in index.sorted_packages():
        lines, package_references[package] = _build_package_diagram(
            package, variant.select_relations, index, skinparam_lines,
        )
        write_file(views_path / f"{index.file_names[package]}{PUML_SUFFIX}", lines)

    overview = _build_overview_diagram(index, package_references, skinparam_lines)
    write_file(views_path / f"{OVERVIEW_NAME}{PUML_SUFFIX}", overview)
    project = _build_project_diagram(index, variant.select_relations, skinparam_lines)
    write_file(views_path / f"{PROJECT_NAME}{PUML_SUFFIX}", project)


def generate_package_views(
    file_diagrams: list[FileDiagram],
    output_base: Path,
    views_dir: str,
    skinparam_lines: list[str],
) -> int:
    """Write every view into output_base/<views_dir> (base) and
    output_base/<views_dir>-Full. Returns the number of packages."""
    index = _build_index(file_diagrams)
    for variant in _VARIANTS:
        _write_views(index, variant, output_base / f"{views_dir}{variant.dir_suffix}", skinparam_lines)
    return len(index.files_by_package)
