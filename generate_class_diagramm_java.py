#!/usr/bin/env python3
"""
generate_class_diagramm_java.py
Reads every .java file under <src_dir> and writes:
  Modelisation/ClassDiagram/    — one .puml per file, extends/implements only
  Modelisation/Fragments/       — fragment versions (no @startuml/@enduml)
  Modelisation/ClassDiagram-Full/ — same + --> (field) and ..> (method-only) to known types
  Modelisation/Fragments-Full/    — fragment versions of the full diagrams
"""

import re
import sys
from pathlib import Path

from java_diagram.source_parsing import find_type_decls, strip_comments, strip_strings
from java_diagram.members import has, parse_members, parse_record_components
from java_diagram.type_format import uml_type
from java_diagram.relations import build_uses_rels
from java_diagram.render import assemble, class_stereotype, gen_enum, gen_interface, puml_name, write_file


def generate_puml(
    java_path: Path,
    out_path: Path,
    frag_path: Path,
    full_out_path: Path | None = None,
    full_frag_path: Path | None = None,
    known_types: set[str] | None = None,
) -> bool:
    raw = java_path.read_text(encoding="utf-8", errors="replace")
    src = strip_strings(strip_comments(raw))

    pkg_m = re.search(r"\bpackage\s+([\w.]+)\s*;", src)
    package = pkg_m.group(1) if pkg_m else None

    decls = find_type_decls(src)
    if not decls:
        return False

    inner_lines: list[str] = []
    rels: list[str] = []
    inherit_by_left: dict[str, set[str]] = {}

    for d in decls:
        kind = d["kind"]
        name = d["name"]
        mods = d["mods"]
        body = d["body"]
        base_class = d["base_class"]
        ifaces = d["interfaces"]

        if kind == "enum":
            gen_enum(name, body, inner_lines)
        elif kind == "interface":
            gen_interface(name, body, inner_lines)
        elif kind == "record":
            stereo = class_stereotype(mods, kind)
            inner_lines.append(f"class {name} {stereo} {{")
            for component_name, component_type in parse_record_components(d["record_params"]):
                inner_lines.append(f"  + {component_name} : {uml_type(component_type)}")
            fields, methods = parse_members(body, name)
            for f in fields:
                inner_lines.append(f"  {f}")
            for m in methods:
                inner_lines.append(f"  {m}")
            inner_lines.append("}")
        else:
            stereo = class_stereotype(mods, kind)
            stereo_str = f" {stereo}" if stereo else ""
            prefix = "abstract " if has(mods, "abstract") else ""
            inner_lines.append(f"{prefix}class {name}{stereo_str} {{")
            fields, methods = parse_members(body, name)
            for f in fields:
                inner_lines.append(f"  {f}")
            for m in methods:
                inner_lines.append(f"  {m}")
            inner_lines.append("}")

        # Left side: strip type params — PlantUML registers 'class Foo<T>' as 'Foo'
        left = name.split("<")[0]
        targets: set[str] = set()
        if base_class:
            t = puml_name(base_class)
            rels.append(f"{left} --|> {t}")
            targets.add(t)
        for iface in ifaces:
            t = puml_name(iface)
            rels.append(f"{left} ..|> {t}")
            targets.add(t)
        inherit_by_left[left] = targets

    # Base output (extends/implements only)
    base_all, base_body = assemble(java_path.stem, package, inner_lines, rels, [])
    write_file(out_path, base_all)
    write_file(frag_path, base_body)

    # Full output (adds *-->, -->, ..> for project types used in members)
    if known_types is not None and full_out_path is not None and full_frag_path is not None:
        compose_rels, other_rels = build_uses_rels(decls, known_types, inherit_by_left)

        if compose_rels:
            base_all, base_body = assemble(java_path.stem, package, inner_lines, rels, compose_rels)
            write_file(out_path, base_all)
            write_file(frag_path, base_body)

        full_all, full_body = assemble(java_path.stem, package, inner_lines, rels, compose_rels + other_rels)
        write_file(full_out_path, full_all)
        write_file(full_frag_path, full_body)

    return True


# ── Entry point ───────────────────────────────────────────────────────────────

_STATUS_OK = "OK"
_STATUS_SKIPPED = "SKIPPED"
_STATUS_ERROR = "ERROR"


def _generate_one(java_file: Path, src_root: Path, out_dirs: tuple[Path, Path, Path, Path], known_types: set[str]) -> str:
    """Generate all four diagram variants for one file. Returns a status string
    and prints the per-file result line."""
    out_root, frag_root, full_out_root, full_frag_root = out_dirs
    rel = java_file.relative_to(src_root)
    out = out_root / rel.with_suffix(".puml")
    frag = frag_root / rel.with_suffix(".puml")
    full_out = full_out_root / rel.with_suffix(".puml")
    full_frag = full_frag_root / rel.with_suffix(".puml")

    try:
        if generate_puml(java_file, out, frag, full_out, full_frag, known_types):
            print(f"  OK     {rel}")
            return _STATUS_OK
        print(f"  SKIP   {rel}  (no type declarations)")
        return _STATUS_SKIPPED
    except Exception as exc:
        print(f"  ERROR  {rel}  — {exc}")
        return _STATUS_ERROR


def _collect_known_types(java_files: list[Path]) -> set[str]:
    known_types: set[str] = set()
    for jf in java_files:
        try:
            raw = jf.read_text(encoding="utf-8", errors="replace")
            src = strip_strings(strip_comments(raw))
            for d in find_type_decls(src):
                known_types.add(d["name"].split("<")[0])
        except Exception:
            pass
    return known_types


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: generate_class_diagramm_java.py <src_dir> [out_dir]")
        print("  src_dir  — directory to search recursively for .java files")
        print("  out_dir  — output root (default: <src_dir>/Modelisation)")
        sys.exit(1)

    src_root = Path(sys.argv[1])
    out_base = Path(sys.argv[2]) if len(sys.argv) > 2 else src_root / "Modelisation"

    out_root = out_base / "ClassDiagram"
    frag_root = out_base / "Fragments"
    full_out_root = out_base / "ClassDiagram-Full"
    full_frag_root = out_base / "Fragments-Full"

    java_files = sorted(src_root.rglob("*.java"))
    print(f"Found {len(java_files)} .java files under {src_root}")

    known_types = _collect_known_types(java_files)
    print(f"  {len(known_types)} known project types for uses-detection")

    out_dirs = (out_root, frag_root, full_out_root, full_frag_root)
    results = [_generate_one(jf, src_root, out_dirs, known_types) for jf in java_files]

    ok = results.count(_STATUS_OK)
    skipped = results.count(_STATUS_SKIPPED)
    errors = results.count(_STATUS_ERROR)
    print(f"\nDone: {ok} generated, {skipped} skipped, {errors} errors.")


if __name__ == "__main__":
    main()
