"""Parse a single Java file into its diagram parts exactly once: package,
declared type names, rendered class/enum/interface blocks, and relation
lines. The per-file writer and the package-level aggregator both consume
this so a file is never parsed twice."""

import re
from pathlib import Path

from .members import has, parse_members, parse_record_components
from .relations import build_uses_rels
from .render import class_stereotype, gen_enum, gen_interface, puml_name
from .source_parsing import find_type_decls, strip_comments, strip_strings
from .type_format import uml_type


class FileDiagram:
    def __init__(
        self,
        stem: str,
        package: str | None,
        decl_names: set[str],
        inner_lines: list[str],
        rels: list[str],
        compose_rels: list[str],
        other_rels: list[str],
    ):
        self.stem = stem
        self.package = package
        self.decl_names = decl_names
        self.inner_lines = inner_lines
        self.rels = rels
        self.compose_rels = compose_rels
        self.other_rels = other_rels


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


def build_file_diagram(java_path: Path, known_types: set[str]) -> FileDiagram | None:
    raw = java_path.read_text(encoding="utf-8", errors="replace")
    src = strip_strings(strip_comments(raw))

    pkg_m = re.search(r"\bpackage\s+([\w.]+)\s*;", src)
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

    compose_rels, other_rels = build_uses_rels(decls, known_types, inherit_by_left)

    return FileDiagram(
        stem=java_path.stem,
        package=package,
        decl_names=decl_names,
        inner_lines=inner_lines,
        rels=rels,
        compose_rels=compose_rels,
        other_rels=other_rels,
    )
