"""Aggregate per-file diagrams into per-package "module" diagrams, plus a
package-level overview that links them together.

The Java package (i.e. the physical folder) is the only grouping unit that
can be derived from source without guessing intent — there's no reliable
way to infer which packages form a logical "module" together, so each
package gets its own diagram and the overview just shows how they reference
each other.
"""

import re
from pathlib import Path

from .render import SKINPARAM_LINES, write_file
from .file_diagram import FileDiagram

_DEFAULT_PACKAGE = "default_package"
_EXTERNAL_SKINPARAM = [
    "skinparam class {",
    "  BackgroundColor<<external>> #EAECEE",
    "  BorderColor<<external>> #839192",
    "}",
]


def _display_name(package: str | None) -> str:
    return package if package else _DEFAULT_PACKAGE


def _file_names_by_package(packages: set[str]) -> dict[str, str]:
    """Short, readable filename per package: the last path segment, unless
    two different packages share it — then fall back to the full path."""
    last_segment = {pkg: pkg.split(".")[-1] for pkg in packages}
    segment_counts: dict[str, int] = {}
    for seg in last_segment.values():
        segment_counts[seg] = segment_counts.get(seg, 0) + 1
    return {
        pkg: seg if segment_counts[seg] == 1 else pkg
        for pkg, seg in last_segment.items()
    }


def _relation_target(rel_line: str) -> str:
    return rel_line.split()[-1]


def _alias(package: str) -> str:
    return re.sub(r"\W", "_", package)


def _group_by_package(file_diagrams: list[FileDiagram]) -> dict[str, list[FileDiagram]]:
    files_by_package: dict[str, list[FileDiagram]] = {}
    for fd in file_diagrams:
        files_by_package.setdefault(_display_name(fd.package), []).append(fd)
    return files_by_package


def _build_type_package_index(files_by_package: dict[str, list[FileDiagram]]) -> dict[str, str]:
    type_package: dict[str, str] = {}
    for pkg, fds in files_by_package.items():
        for fd in fds:
            for name in fd.decl_names:
                type_package[name] = pkg
    return type_package


def _build_one_package_diagram(
    pkg: str,
    fds: list[FileDiagram],
    type_package: dict[str, str],
    file_names: dict[str, str],
) -> tuple[list[str], set[str]]:
    """Returns (puml_lines, referenced_packages) for one package's diagram."""
    own_names: set[str] = set()
    for fd in fds:
        own_names |= fd.decl_names

    inner_lines: list[str] = []
    rels: list[str] = []
    external_stubs: dict[str, str] = {}  # target name -> target package
    referenced_packages: set[str] = set()

    for fd in fds:
        inner_lines.extend(fd.inner_lines)
        for rel_line in fd.rels + fd.compose_rels + fd.other_rels:
            rels.append(rel_line)
            target = _relation_target(rel_line)
            if target in own_names:
                continue
            target_pkg = type_package.get(target)
            if target_pkg is None or target_pkg == pkg:
                continue
            external_stubs[target] = target_pkg
            referenced_packages.add(target_pkg)

    rels = list(dict.fromkeys(rels))  # de-dup while keeping first-seen order

    for target, target_pkg in sorted(external_stubs.items()):
        inner_lines.append(f"class {target} <<external>> [[{file_names[target_pkg]}.svg]] {{")
        inner_lines.append("}")

    body = (
        [f"@startuml {file_names[pkg]}", ""]
        + SKINPARAM_LINES
        + [""]
        + _EXTERNAL_SKINPARAM
        + [""]
        + inner_lines
        + [""]
        + rels
        + ["", "@enduml"]
    )
    return body, referenced_packages


def _build_overview_diagram(
    files_by_package: dict[str, list[FileDiagram]],
    file_names: dict[str, str],
    package_refs: dict[str, set[str]],
) -> list[str]:
    lines = ["@startuml _overview", ""] + SKINPARAM_LINES + [""]
    for pkg in sorted(files_by_package):
        lines.append(f'package "{pkg}" as {_alias(pkg)} [[{file_names[pkg]}.svg]] {{')
        lines.append("}")
    lines.append("")
    for pkg in sorted(files_by_package):
        for target_pkg in sorted(package_refs.get(pkg, set())):
            lines.append(f"{_alias(pkg)} ..> {_alias(target_pkg)}")
    lines += ["", "@enduml"]
    return lines


def generate_package_diagrams(file_diagrams: list[FileDiagram], out_dir: Path) -> int:
    """Write one aggregate diagram per package plus an overview diagram
    linking them. Returns the number of package diagrams written."""
    files_by_package = _group_by_package(file_diagrams)
    file_names = _file_names_by_package(set(files_by_package))
    type_package = _build_type_package_index(files_by_package)

    package_refs: dict[str, set[str]] = {}
    for pkg, fds in files_by_package.items():
        body, referenced_packages = _build_one_package_diagram(pkg, fds, type_package, file_names)
        write_file(out_dir / f"{file_names[pkg]}.puml", body)
        package_refs[pkg] = referenced_packages

    overview = _build_overview_diagram(files_by_package, file_names, package_refs)
    write_file(out_dir / "_overview.puml", overview)

    return len(files_by_package)
