"""Parse a single Java file into its diagram parts exactly once: package,
declared type names, rendered class/enum/interface blocks, and relation
lines. The per-file writer and the package views both consume this so a
file is never parsed twice."""

import re
from pathlib import Path

from diagram_common.file_diagram import FileDiagram

from .members import has, parse_members, parse_record_components
from .relations import build_uses_rels
from .render import class_stereotype, gen_enum, gen_interface, puml_name
from .source_parsing import find_type_decls, strip_comments, strip_strings
from .type_format import uml_type


PACKAGE_RE = re.compile(r"\bpackage\s+([\w.]+)\s*;")
# Package segments are lowercase by convention; the first capitalized
# segment starts the type path, so a nested-type import like
# 'a.b.Outer.Inner' resolves Inner to package 'a.b', not to 'a.b.Outer' —
# a class name used as a namespace crashes PlantUML.
IMPORT_RE = re.compile(
    r"^\s*import\s+(?!static\b)((?:[a-z_]\w*\.)*[a-z_]\w*)\.(?:[A-Z]\w*\.)*([A-Z]\w*)\s*;",
    re.MULTILINE,
)


def _render_type(d: dict, inner_lines: list[str]) -> None:
    kind = d["kind"]
    name = d["name"]
    mods = d["mods"]
    body = d["body"]

    if kind == "enum":
        gen_enum(name, body, inner_lines)
        return
    if kind == "interface":
        gen_interface(name, body, inner_lines)
        return

    stereo = class_stereotype(mods, kind)
    if kind == "record":
        inner_lines.append(f"class {name} {stereo} {{")
        for component_name, component_type in parse_record_components(d["record_params"]):
            inner_lines.append(f"  + {component_name} : {uml_type(component_type)}")
    else:
        stereo_str = f" {stereo}" if stereo else ""
        prefix = "abstract " if has(mods, "abstract") else ""
        inner_lines.append(f"{prefix}class {name}{stereo_str} {{")

    fields, methods = parse_members(body, name)
    for f in fields:
        inner_lines.append(f"  {f}")
    for m in methods:
        inner_lines.append(f"  {m}")
    inner_lines.append("}")


def _parse_imports(src: str) -> dict[str, str]:
    """Simple name -> package for each single-type import (wildcard and
    static imports name no single type, so they're skipped)."""
    return {m.group(2): m.group(1) for m in IMPORT_RE.finditer(src)}


def _resolve_package(
    name: str,
    own_package: str | None,
    own_names: set[str],
    imports: dict[str, str],
    type_packages: dict[str, set[str | None]],
) -> str | None:
    """Package a referenced type lives in, or None when it can't be
    determined (unknown type, or a simple name declared in several packages
    with nothing to disambiguate) — such types are drawn outside any package
    rather than guessed into one."""
    if name in own_names:
        return own_package
    if name in imports:
        return imports[name]
    candidates = type_packages.get(name, set())
    if own_package in candidates:
        return own_package
    if len(candidates) == 1:
        return next(iter(candidates))
    return None


def _rel_names(rel_lines: list[str]) -> set[str]:
    names: set[str] = set()
    for line in rel_lines:
        tokens = line.split(" ")
        names.add(tokens[0])
        names.add(tokens[-1])
    return names


def build_file_diagram(
    java_path: Path,
    type_packages: dict[str, set[str | None]],
) -> FileDiagram | None:
    """type_packages maps every project type's simple name to the package(s)
    declaring it."""
    raw = java_path.read_text(encoding="utf-8", errors="replace")
    src = strip_strings(strip_comments(raw))

    pkg_m = PACKAGE_RE.search(src)
    package = pkg_m.group(1) if pkg_m else None

    decls = find_type_decls(src)
    if not decls:
        return None

    inner_lines: list[str] = []
    rels: list[str] = []
    inherit_by_left: dict[str, set[str]] = {}
    decl_names: set[str] = set()

    for d in decls:
        _render_type(d, inner_lines)

        # Left side: strip type params — PlantUML registers 'class Foo<T>' as 'Foo'
        left = d["name"].split("<")[0]
        decl_names.add(left)
        targets: set[str] = set()
        if d["base_class"]:
            t = puml_name(d["base_class"])
            rels.append(f"{left} --|> {t}")
            targets.add(t)
        for iface in d["interfaces"]:
            t = puml_name(iface)
            rels.append(f"{left} ..|> {t}")
            targets.add(t)
        inherit_by_left[left] = targets

    compose_rels, other_rels = build_uses_rels(decls, set(type_packages), inherit_by_left)

    imports = _parse_imports(src)
    name_packages = {
        name: _resolve_package(name, package, decl_names, imports, type_packages)
        for name in _rel_names(rels + compose_rels + other_rels)
    }

    return FileDiagram(
        stem=java_path.stem,
        package=package,
        decl_names=decl_names,
        inner_lines=inner_lines,
        rels=rels,
        compose_rels=compose_rels,
        other_rels=other_rels,
        name_packages=name_packages,
    )
