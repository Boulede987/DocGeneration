#!/usr/bin/env python3
"""
generate_puml_unity.py
Unity-specific class diagram generator.

Extends the generic generate_puml with:
  - Unity type primitives (MonoBehaviour, Transform, Vector3, ...)
  - MonoBehaviour / ScriptableObject base-class filtering
  - [SerializeField] → aggregation logic
  - <<scriptableObject>> stereotype and skinparam
  - Transitive ScriptableObject subclass detection

Usage:
    python generate_puml_unity.py <src_dir> [out_dir]
"""

import re
import sys
from pathlib import Path

# ── Import stable parsing utilities from generic script ───────────────────────
from generate_class_diagramm import (
    _strip_comments, _strip_strings,
    _find_type_decls, _flatten, _split_bases,
    _ATTR_PREFIX, _PROP_RE, _METHOD_RE, _FIELD_RE,
    _has, _parse_members, _puml_name,
    _is_collection_type,
    _iter_method_bodies, _scan_body_types, _collect_newed_types,
    _gen_enum, _gen_interface,
    _parse_namespace, _collect_type_namespaces, _qualify_rels,
)
import generate_class_diagramm as _gp


# ── Unity-specific constants ──────────────────────────────────────────────────

_UNITY_BASES = frozenset({
    "MonoBehaviour", "ScriptableObject", "GameObject", "Component",
})

_PRIMITIVES = _gp._PRIMITIVES | frozenset({
    "GameObject", "MonoBehaviour", "ScriptableObject", "Component",
    "Transform", "Vector2", "Vector3", "Vector4", "Quaternion",
    "Color", "Color32", "Rect", "RectTransform", "Sprite", "Texture2D",
    "Coroutine", "WaitForSeconds", "WaitUntil", "WaitForEndOfFrame",
    "UnityEvent", "SerializeField", "RequireComponent",
    "Debug", "Mathf", "Resources", "Addressables",
    "AssetReference", "AsyncOperationHandle",
})

_SKINPARAM_LINES = [
    "skinparam classAttributeIconSize 0",
    "skinparam shadowing false",
    "",
    "skinparam class {",
    "  BackgroundColor<<interface>> #D6EAF8",
    "  BorderColor<<interface>> #2E86C1",
    "}",
    "skinparam class {",
    "  BackgroundColor<<abstract>> #E8DAEF",
    "  BorderColor<<abstract>> #8E44AD",
    "}",
    "skinparam class {",
    "  BackgroundColor #D5F5E3",
    "  BorderColor #27AE60",
    "}",
    "skinparam class {",
    "  BackgroundColor<<struct>> #FAD7A0",
    "  BorderColor<<struct>> #D68910",
    "}",
    "skinparam class {",
    "  BackgroundColor<<static>> #a7faa0",
    "  BorderColor<<static>> #38d610",
    "}",
    "skinparam class {",
    "  BackgroundColor<<scriptableObject>> #d6a0fa",
    "  BorderColor<<scriptableObject>> #d61094",
    "}",
    "skinparam class {",
    "  BackgroundColor<<enum>> #F5B7B1",
    "  BorderColor<<enum>> #C0392B",
    "}",
]


# ── Unity-specific overrides ──────────────────────────────────────────────────

def _extract_type_names(type_str: str) -> set[str]:
    type_str = type_str.rstrip("?")
    tokens = re.split(r"[<>,\[\]\s\.\*\(\)]+", type_str)
    return {
        t for t in tokens
        if t and re.match(r"^[A-Z]\w*$", t) and t not in _PRIMITIVES
    }


def _class_stereotype(mods: str, base_class: str | None, kind: str) -> str:
    if kind == "struct":
        return "<<struct>>"
    if base_class == "ScriptableObject":
        return "<<scriptableObject>>"
    if _has(mods, "abstract"):
        return "<<abstract>>"
    if _has(mods, "static"):
        return "<<static>>"
    return ""


def _extract_member_types(body: str, name: str) -> tuple[list[tuple[str, bool, bool]], list[str]]:
    """Returns (field_prop_items, method_types).
    field_prop_items: (type_str, is_public, is_serialized)
      is_serialized: [SerializeField] attribute present → treat as aggregation
    """
    base = name.split("<")[0]
    field_prop: list[tuple[str, bool, bool]] = []
    method: list[str] = []

    for stmt in _flatten(body):
        has_sf = "[SerializeField]" in stmt
        stmt_clean = _ATTR_PREFIX.sub("", stmt).strip()
        if not stmt_clean:
            continue

        if "{ get/set }" in stmt_clean:
            m = _PROP_RE.match(stmt_clean)
            if m:
                field_prop.append((m.group("type"), _has(m.group("mods"), "public"), has_sf))
        elif "(" in stmt_clean:
            m = _METHOD_RE.match(stmt_clean)
            if m and m.group("name") != base:
                method.append(m.group("ret"))
                for param in m.group("params").split(","):
                    param = re.sub(r"^(?:out|ref|in|params)\s+", "", param.strip())
                    parts = param.split()
                    if parts:
                        method.append(parts[0])
        elif stmt_clean.endswith(";"):
            m = _FIELD_RE.match(stmt_clean)
            if m:
                field_prop.append((m.group("type"), _has(m.group("mods"), "public"), has_sf))

    for method_body in _iter_method_bodies(body):
        method.extend(_scan_body_types(method_body))

    return field_prop, method


def _build_uses_rels(
    decls: list[dict],
    known_types: set[str],
    inherit_rels_by_left: dict[str, set[str]],
    known_scriptable_objects: set[str],
) -> tuple[list[str], list[str]]:
    """
    Composition (*-->): newed in code AND not a ScriptableObject.
    Aggregation (o-->): public OR [SerializeField] OR ScriptableObject-typed field.
    Association (-->):  private field, not newed.
    Dependency  (..>):  type appears only in method signatures or bodies.
    """
    compose_rels: list[str] = []
    other_rels:   list[str] = []

    for d in decls:
        if d["kind"] not in ("class", "struct"):
            continue

        left    = d["name"].split("<")[0]
        already = inherit_rels_by_left.get(left, set())

        fp_items, mt_types = _extract_member_types(d["body"], d["name"])
        newed_types = _collect_newed_types(d["body"])

        field_info: dict[str, dict[str, bool]] = {}
        for type_str, is_pub, is_sf in fp_items:
            is_coll = _is_collection_type(type_str)
            for tn in _extract_type_names(type_str):
                if tn in known_types and tn != left and tn not in already:
                    if tn not in field_info:
                        field_info[tn] = {"is_coll": False, "is_public": False, "is_serialized": False}
                    fi = field_info[tn]
                    fi["is_coll"]       = fi["is_coll"]       or is_coll
                    fi["is_public"]     = fi["is_public"]     or is_pub
                    fi["is_serialized"] = fi["is_serialized"] or is_sf

        dep_set: set[str] = set()
        for t in mt_types:
            for tn in _extract_type_names(t):
                if tn in known_types and tn != left and tn not in already and tn not in field_info:
                    dep_set.add(tn)

        for tn in sorted(field_info):
            fi   = field_info[tn]
            mult = ' "0..*"' if fi["is_coll"] else ""
            if tn in known_scriptable_objects:
                other_rels.append(f"{left} o-->{mult} {tn}")
            elif tn in newed_types or fi["is_public"] or fi["is_serialized"]:
                compose_rels.append(f"{left} *-->{mult} {tn}")
            else:
                other_rels.append(f"{left} -->{mult} {tn}")
        for tn in sorted(dep_set):
            other_rels.append(f"{left} ..> {tn}")

    return compose_rels, other_rels


def _assemble(
    stem: str,
    namespace: str | None,
    inner_lines: list[str],
    rels: list[str],
    extra_rels: list[str],
) -> tuple[list[str], list[str]]:
    """Relation lines go after the namespace block and must use
    fully-qualified names — see generate_class_diagramm._assemble."""
    body: list[str] = []
    if namespace:
        body.append(f"namespace {namespace} {{")
    body.extend(inner_lines)
    if namespace:
        body.append("}")
    body.append("")
    body.extend(rels)
    if extra_rels:
        body.extend(extra_rels)
    full = [f"@startuml {stem}", ""] + _SKINPARAM_LINES + [""] + body + ["", "@enduml"]
    return full, body


# ── Main generation function ──────────────────────────────────────────────────

def generate_puml(
    cs_path: Path,
    out_path: Path,
    frag_path: Path,
    full_out_path: Path | None = None,
    full_frag_path: Path | None = None,
    type_namespaces: dict[str, set[str | None]] | None = None,
    known_scriptable_objects: set[str] | None = None,
) -> bool:
    """type_namespaces maps every project type's simple name to the
    namespace(s) declaring it; without it, only the base diagram is written."""
    raw = cs_path.read_text(encoding="utf-8", errors="replace")
    src = _strip_strings(_strip_comments(raw))

    namespace = _parse_namespace(src)

    decls = _find_type_decls(src)
    if not decls:
        return False

    inner_lines: list[str] = []
    rels: list[str] = []
    inherit_by_left: dict[str, set[str]] = {}

    for d in decls:
        kind       = d["kind"]
        name       = d["name"]
        mods       = d["mods"]
        body       = d["body"]
        base_class, ifaces = _split_bases(d["bases"])

        if kind == "enum":
            _gen_enum(name, body, inner_lines)
        elif kind == "interface":
            _gen_interface(name, body, inner_lines)
        else:
            stereo     = _class_stereotype(mods, base_class, kind)
            stereo_str = f" {stereo}" if stereo else ""
            prefix     = "abstract " if _has(mods, "abstract") else ""
            inner_lines.append(f"{prefix}class {name}{stereo_str} {{")
            fields, props, methods = _parse_members(body, name)
            for f in fields:
                inner_lines.append(f"  {f}")
            for p in props:
                inner_lines.append(f"  {p}")
            for m in methods:
                inner_lines.append(f"  {m}")
            inner_lines.append("}")

        left    = name.split("<")[0]
        targets: set[str] = set()
        if base_class:
            t = _puml_name(base_class)
            if t not in _UNITY_BASES:
                rels.append(f"{left} --|> {t}")
            targets.add(t)
        for iface in ifaces:
            t = _puml_name(iface)
            rels.append(f"{left} ..|> {t}")
            targets.add(t)
        inherit_by_left[left] = targets

    own_names = set(inherit_by_left)

    def qualify(rel_lines: list[str]) -> list[str]:
        return _qualify_rels(rel_lines, namespace, own_names, src, type_namespaces or {})

    rels = qualify(rels)

    base_all, base_body = _assemble(cs_path.stem, namespace, inner_lines, rels, [])

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(base_all), encoding="utf-8")
    frag_path.parent.mkdir(parents=True, exist_ok=True)
    frag_path.write_text("\n".join(base_body), encoding="utf-8")

    if type_namespaces is not None and full_out_path is not None and full_frag_path is not None:
        so_set = known_scriptable_objects or set()
        compose_rels, other_rels = _build_uses_rels(decls, set(type_namespaces), inherit_by_left, so_set)
        compose_rels = qualify(compose_rels)
        other_rels = qualify(other_rels)

        if compose_rels:
            base_all, base_body = _assemble(cs_path.stem, namespace, inner_lines, rels, compose_rels)
            out_path.write_text("\n".join(base_all), encoding="utf-8")
            frag_path.write_text("\n".join(base_body), encoding="utf-8")

        full_all, full_body = _assemble(
            cs_path.stem, namespace, inner_lines, rels, compose_rels + other_rels
        )
        full_out_path.parent.mkdir(parents=True, exist_ok=True)
        full_out_path.write_text("\n".join(full_all), encoding="utf-8")
        full_frag_path.parent.mkdir(parents=True, exist_ok=True)
        full_frag_path.write_text("\n".join(full_body), encoding="utf-8")

    return True


# ── Entry point ────────────────────────────────────────────────────────────────

def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: generate_puml_unity.py <src_dir> [out_dir]")
        print("  src_dir  — directory to search recursively for .cs files")
        print("  out_dir  — output root (default: <src_dir>/Modelisation)")
        sys.exit(1)

    src_root = Path(sys.argv[1])
    out_base = Path(sys.argv[2]) if len(sys.argv) > 2 else src_root / "Modelisation"

    out_root       = out_base / "ClassDiagram"
    frag_root      = out_base / "Fragments"
    full_out_root  = out_base / "ClassDiagram-Full"
    full_frag_root = out_base / "Fragments-Full"

    cs_files = sorted(src_root.rglob("*.cs"))
    print(f"Found {len(cs_files)} .cs files under {src_root}")

    # First pass: collect all declared type names, their namespaces and direct base classes
    type_namespaces = _collect_type_namespaces(cs_files)
    type_bases:  dict[str, str | None] = {}
    for cs in cs_files:
        try:
            raw = cs.read_text(encoding="utf-8", errors="replace")
            src = _strip_strings(_strip_comments(raw))
            for d in _find_type_decls(src):
                n = d["name"].split("<")[0]
                bc, _ = _split_bases(d["bases"])
                type_bases[n] = bc.split("<")[0] if bc else None
        except Exception:
            pass
    print(f"  {len(type_namespaces)} known project types")

    # Transitive ScriptableObject subclass detection
    known_so: set[str] = {n for n, b in type_bases.items() if b == "ScriptableObject"}
    changed = True
    while changed:
        changed = False
        for n, b in type_bases.items():
            if n not in known_so and b in known_so:
                known_so.add(n)
                changed = True
    print(f"  {len(known_so)} ScriptableObject subclasses: {sorted(known_so)}")

    ok = skipped = errors = 0
    for cs in cs_files:
        rel       = cs.relative_to(src_root)
        out       = out_root       / rel.with_suffix(".puml")
        frag      = frag_root      / rel.with_suffix(".puml")
        full_out  = full_out_root  / rel.with_suffix(".puml")
        full_frag = full_frag_root / rel.with_suffix(".puml")
        try:
            if generate_puml(cs, out, frag, full_out, full_frag, type_namespaces, known_so):
                print(f"  OK     {rel}")
                ok += 1
            else:
                print(f"  SKIP   {rel}  (no type declarations)")
                skipped += 1
        except Exception as exc:
            print(f"  ERROR  {rel}  — {exc}")
            errors += 1

    print(f"\nDone: {ok} generated, {skipped} skipped, {errors} errors.")


if __name__ == "__main__":
    main()
