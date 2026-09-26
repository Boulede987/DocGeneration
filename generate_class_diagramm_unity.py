#!/usr/bin/env python3
"""
generate_class_diagramm_unity.py
Unity-specific class diagram generator. Writes the same outputs as
generate_class_diagramm.py (per-file diagrams plus Namespaces/ views).

Extends the generic generate_class_diagramm with:
  - Unity type primitives (MonoBehaviour, Transform, Vector3, ...)
  - MonoBehaviour / ScriptableObject base-class filtering
  - [SerializeField] → aggregation logic
  - <<scriptableObject>> stereotype and skinparam
  - Transitive ScriptableObject subclass detection

Usage:
    python generate_class_diagramm_unity.py <src_dir> [out_dir]
"""

import re
import sys
from functools import partial
from pathlib import Path

# ── Import stable parsing utilities from generic script ───────────────────────
from generate_class_diagramm import (
    _strip_comments, _strip_strings,
    _find_type_decls, _flatten, _split_bases,
    _ATTR_PREFIX, _PROP_RE, _METHOD_RE, _FIELD_RE,
    _has, _is_collection_type,
    _iter_method_bodies, _scan_body_types, _collect_newed_types,
    _collect_type_namespaces,
    GeneratorRules, generate_all,
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


# ── Entry point ────────────────────────────────────────────────────────────────

def _collect_type_bases(cs_files: list[Path]) -> dict[str, str | None]:
    """Simple name -> direct base class name, for every project type."""
    type_bases: dict[str, str | None] = {}
    for cs in cs_files:
        try:
            raw = cs.read_text(encoding="utf-8", errors="replace")
            src = _strip_strings(_strip_comments(raw))
            for d in _find_type_decls(src):
                bc, _ = _split_bases(d["bases"])
                type_bases[d["name"].split("<")[0]] = bc.split("<")[0] if bc else None
        except Exception:
            pass
    return type_bases


def _scriptable_object_subclasses(type_bases: dict[str, str | None]) -> set[str]:
    """Every project type inheriting ScriptableObject, directly or transitively."""
    known_so: set[str] = {n for n, b in type_bases.items() if b == "ScriptableObject"}
    changed = True
    while changed:
        changed = False
        for n, b in type_bases.items():
            if n not in known_so and b in known_so:
                known_so.add(n)
                changed = True
    return known_so


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: generate_class_diagramm_unity.py <src_dir> [out_dir]")
        print("  src_dir  — directory to search recursively for .cs files")
        print("  out_dir  — output root (default: <src_dir>/Modelisation)")
        sys.exit(1)

    src_root = Path(sys.argv[1])
    out_base = Path(sys.argv[2]) if len(sys.argv) > 2 else src_root / "Modelisation"

    cs_files = sorted(src_root.rglob("*.cs"))
    print(f"Found {len(cs_files)} .cs files under {src_root}")

    type_namespaces = _collect_type_namespaces(cs_files)
    print(f"  {len(type_namespaces)} known project types")

    known_so = _scriptable_object_subclasses(_collect_type_bases(cs_files))
    print(f"  {len(known_so)} ScriptableObject subclasses: {sorted(known_so)}")

    rules = GeneratorRules(
        class_stereotype=_class_stereotype,
        build_uses_rels=partial(_build_uses_rels, known_scriptable_objects=known_so),
        hidden_bases=_UNITY_BASES,
    )
    generate_all(src_root, cs_files, out_base, type_namespaces, rules, _SKINPARAM_LINES)


if __name__ == "__main__":
    main()
