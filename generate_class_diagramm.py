#!/usr/bin/env python3
"""
generate_class_diagramm.py
Reads every .cs file under <src_dir> and writes:
  Modelisation/ClassDiagram/    — one .puml per file, inherits/implements + composition
  Modelisation/Fragments/       — fragment versions (no @startuml/@enduml)
  Modelisation/ClassDiagram-Full/ — same + --> (field/prop) and ..> (method-only) to known types
  Modelisation/Fragments-Full/    — fragment versions of the full diagrams
  Modelisation/Namespaces/      — one diagram per namespace, an _overview.puml
                                  linking them, and a _project.puml with every class
  Modelisation/Namespaces-Full/ — same views with every relation
"""

import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from diagram_common.file_diagram import FileDiagram, FileOutputPaths, relation_ends, write_file_outputs
from diagram_common.package_views import generate_package_views

# ── Modifier keywords ─────────────────────────────────────────────────────────

_MODS = frozenset({
    "public", "private", "protected", "internal", "abstract", "sealed",
    "static", "readonly", "const", "new", "virtual", "override", "extern",
    "async", "volatile", "unsafe", "event", "partial", "required",
})

_MODS_PAT = (
    r"(?P<mods>"
    r"(?:(?:public|private|protected|internal|abstract|sealed|static|"
    r"readonly|const|new|virtual|override|extern|async|volatile|unsafe|"
    r"event|partial|required)\s+)+"
    r")"
)

_VIS_RULES = [
    ("private protected", "-"),
    ("protected internal", "#"),
    ("private", "-"),
    ("protected", "#"),
    ("public", "+"),
    ("internal", "~"),
]


def _vis(mods: str) -> str:
    for key, sym in _VIS_RULES:
        if key in mods:
            return sym
    return "~"


def _has(mods: str, *flags) -> bool:
    words = set(mods.split())
    return any(f in words for f in flags)


# ── Source pre-processing ─────────────────────────────────────────────────────

def _strip_comments(src: str) -> str:
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.DOTALL)
    src = re.sub(r"//[^\n]*", "", src)
    return src


def _strip_strings(src: str) -> str:
    # Verbatim strings (may contain {})
    src = re.sub(r'@"[^"]*(?:""[^"]*)*"', '""', src)
    # Interpolated + regular strings
    src = re.sub(r'"(?:\\.|[^"\\])*"', '""', src)
    # Char literals
    src = re.sub(r"'(?:\\.|[^'\\])+'", "''", src)
    return src


# ── Brace utilities ───────────────────────────────────────────────────────────

def _close_brace(src: str, open_pos: int) -> int:
    """Return index of } that matches { at open_pos."""
    depth = 0
    for i in range(open_pos, len(src)):
        c = src[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i
    return len(src) - 1


# ── Type-declaration finder ───────────────────────────────────────────────────

_TYPE_DECL = re.compile(
    r"(?:(?:\[[^\]]*\]\s*)*)"                   # optional attributes
    r"(?P<mods>"
    r"(?:(?:public|private|protected|internal|"
    r"abstract|sealed|static|partial|new|readonly)\s+)+"
    r")"
    r"(?P<kind>class|interface|enum|struct)\s+"
    r"(?P<name>\w+(?:\s*<[^>]+>)?)"             # name with optional <T>
    r"(?:\s*:\s*(?P<bases>[^{]+?))?"            # optional : bases
    r"\s*\{",
    re.DOTALL,
)


def _find_type_decls(src: str) -> list[dict]:
    results = []
    for m in _TYPE_DECL.finditer(src):
        open_pos = m.end() - 1          # the { matched at end of regex
        # Validate
        if src[open_pos] != "{":
            # Regex ended with \s*\{ so last non-space is {; search backward
            open_pos = src.rindex("{", m.start(), m.end())
        close_pos = _close_brace(src, open_pos)
        body = src[open_pos + 1 : close_pos]

        name = re.sub(r"\s+", "", m.group("name"))
        bases_raw = m.group("bases") or ""
        bases = _split_bases_raw(bases_raw)

        results.append(
            {
                "mods": m.group("mods").strip(),
                "kind": m.group("kind"),
                "name": name,
                "bases": bases,
                "body": body,
            }
        )
    return results


# ── Member flattener ──────────────────────────────────────────────────────────

_NESTED_TYPE = re.compile(
    r"\b(?:class|interface|enum|struct)\b"
)
_PROP_INNER = re.compile(r"\b(?:get|set|init)\b")


def _flatten(body: str) -> list[str]:
    """
    Walk the class body and collect member declarations as strings.

    Rules:
    - Hit { at depth 0 → collapse to placeholder (keeps signature).
      If inner text has get/set/init → property, else → method body.
    - Hit ; at depth 0 → field or abstract/expression-body method.
    """
    stmts: list[str] = []
    i = 0
    n = len(body)
    seg_start = 0

    while i < n:
        c = body[i]

        if c == "{":
            sig = body[seg_start:i].strip()
            close = _close_brace(body, i)
            inner = body[i + 1 : close]

            if sig:
                if _NESTED_TYPE.search(sig):
                    pass  # skip nested type declaration
                elif _PROP_INNER.search(inner):
                    stmts.append(sig + " { get/set }")
                else:
                    stmts.append(sig + " {}")

            seg_start = close + 1
            i = close + 1

        elif c == ";":
            seg = body[seg_start:i].strip()
            if seg:
                stmts.append(seg + ";")
            seg_start = i + 1
            i += 1

        else:
            i += 1

    trailing = body[seg_start:].strip()
    if trailing:
        stmts.append(trailing)

    return stmts


# ── Member parser ─────────────────────────────────────────────────────────────

_ATTR_PREFIX = re.compile(r"^(?:\s*\[[^\]]*\]\s*)+")
_PROP_RE = re.compile(
    _MODS_PAT
    + r"(?P<type>[\w<>?,\[\]\.]+)\s+"
    + r"(?P<name>\w+)\s*\{",
)
_METHOD_RE = re.compile(
    _MODS_PAT
    + r"(?P<ret>[\w<>?,\[\]\.]+)\s+"
    + r"(?P<name>\w+)\s*"
    + r"(?:<[^>]+>)?\s*"
    + r"\((?P<params>[^)]*)\)",
)
_FIELD_RE = re.compile(
    _MODS_PAT
    + r"(?P<type>[\w<>?,\[\]\.]+)\s+"
    + r"(?P<name>\w+)",
)


def _simplify_params(raw: str) -> str:
    if not raw.strip():
        return ""
    out = []
    for p in raw.split(","):
        p = re.sub(r"^(?:out|ref|in|params)\s+", "", p.strip())
        parts = p.split()
        if parts:
            out.append(parts[0])
    return ", ".join(out)


def _parse_member(stmt: str, class_base: str):
    """Return (kind, info_dict) or None."""
    stmt = _ATTR_PREFIX.sub("", stmt).strip()
    if not stmt:
        return None

    # Property
    if "{ get/set }" in stmt:
        m = _PROP_RE.match(stmt)
        if m:
            return "property", {
                "mods": m.group("mods").strip(),
                "type": m.group("type"),
                "name": m.group("name"),
            }

    # Method (has parentheses)
    if "(" in stmt:
        m = _METHOD_RE.match(stmt)
        if m:
            name = m.group("name")
            if name == class_base:
                return None  # constructor
            return "method", {
                "mods": m.group("mods").strip(),
                "ret": m.group("ret"),
                "name": name,
                "params": _simplify_params(m.group("params")),
                "params_raw": m.group("params"),
            }

    # Field
    if stmt.endswith(";"):
        m = _FIELD_RE.match(stmt)
        if m:
            return "field", {
                "mods": m.group("mods").strip(),
                "type": m.group("type"),
                "name": m.group("name"),
            }

    return None


def _parse_members(body: str, name: str):
    """Return (fields, props, methods) as lists of PlantUML strings."""
    base = name.split("<")[0]
    fields, props, methods = [], [], []

    for stmt in _flatten(body):
        result = _parse_member(stmt, base)
        if result is None:
            continue
        kind, info = result
        mods = info["mods"]
        vis = _vis(mods)

        extra = []
        if _has(mods, "static", "const"):
            extra.append("{static}")
        if _has(mods, "abstract"):
            extra.append("{abstract}")
        prefix = (" ".join(extra) + " ") if extra else ""

        if kind == "field":
            fields.append(f"{vis} {prefix}{info['name']} : {_uml_type(info['type'])}")
        elif kind == "property":
            props.append(f"{vis} {prefix}{info['name']} : {_uml_type(info['type'])}")
        elif kind == "method":
            params = info["params"]
            ret = info["ret"]
            ret_suffix = "" if ret in ("void", "async void") else f" : {ret}"
            methods.append(
                f"{vis} {prefix}{info['name']}({params}){ret_suffix}"
            )

    return fields, props, methods


# ── Relationship helpers ──────────────────────────────────────────────────────

def _split_bases_raw(raw: str) -> list[str]:
    """Split 'A, B<C,D>, E' by comma respecting <> and () depth."""
    # Strip 'where T : ...' constraints
    raw = re.sub(r"\s+where\b.*$", "", raw, flags=re.DOTALL).strip()
    parts: list[str] = []
    depth = 0
    current: list[str] = []
    for c in raw:
        if c in "<(":
            depth += 1
            current.append(c)
        elif c in ">)":
            depth -= 1
            current.append(c)
        elif c == "," and depth == 0:
            p = "".join(current).strip()
            if p:
                parts.append(p)
            current = []
        else:
            current.append(c)
    p = "".join(current).strip()
    if p:
        parts.append(p)
    return parts


def _puml_name(name: str) -> str:
    """Strip generic parameters from a type name for relationship lines.
    PlantUML registers 'class Foo<T>' as 'Foo', so all cross-file references
    must use the bare name — otherwise !include linking breaks."""
    return name.split("<")[0]


def _split_bases(bases: list[str]):
    """Heuristic: starts with I+uppercase → interface, else base class."""
    base_class = None
    interfaces = []
    for b in bases:
        if re.match(r"^I[A-Z]", b):
            interfaces.append(b)
        elif base_class is None:
            base_class = b
        else:
            interfaces.append(b)
    return base_class, interfaces


# ── Uses/composition detection ────────────────────────────────────────────────

_COLLECTION_WRAPPERS = frozenset({
    "List", "IList", "IEnumerable", "IReadOnlyList", "ICollection",
    "IReadOnlyCollection", "HashSet", "Queue", "Stack", "LinkedList",
    "ObservableCollection", "SortedSet", "SortedList", "ConcurrentBag",
    "ConcurrentQueue", "ConcurrentStack",
})


def _is_collection_type(type_str: str) -> bool:
    t = type_str.rstrip("?")
    if t.endswith("[]"):
        return True
    return t.split("<")[0] in _COLLECTION_WRAPPERS


def _uml_type(type_str: str) -> str:
    """Convert C# collection types to UML multiplicity notation."""
    t = type_str.strip()
    if t.endswith("[]"):
        return t[:-2] + "[*]"
    wrapper = t.split("<")[0]
    if wrapper in _COLLECTION_WRAPPERS:
        inner = t[len(wrapper):]
        if inner.startswith("<") and inner.endswith(">"):
            return inner[1:-1].strip() + "[*]"
    return t


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
    "  BackgroundColor<<enum>> #F5B7B1",
    "  BorderColor<<enum>> #C0392B",
    "}",
]

_PRIMITIVES = frozenset({
    "void", "bool", "int", "float", "double", "long", "short", "byte",
    "uint", "ulong", "ushort", "sbyte", "char", "decimal", "object",
    "string", "dynamic", "var",
    # single-letter generic params
    "T", "U", "V", "K", "TKey", "TValue", "TComponent", "TResult",
    # common BCL containers and types (not project classes)
    "List", "Dictionary", "HashSet", "Queue", "Stack", "Array",
    "IEnumerable", "IList", "ICollection", "IReadOnlyList", "IReadOnlyCollection",
    "Action", "Func", "Predicate", "Delegate", "EventHandler",
    "Task", "ValueTask", "Nullable",
    "Math", "Random",
    "Exception", "ArgumentException", "InvalidOperationException",
    "IDisposable", "IEquatable", "IComparable", "ICloneable",
    "StringBuilder", "Stream", "StreamReader", "StreamWriter",
    "Encoding", "File", "Directory", "Path",
    "JsonConvert", "JObject", "JArray",
    "Type", "Object", "Enum", "Attribute",
})


def _extract_type_names(type_str: str) -> set[str]:
    """Extract bare class names from a possibly generic/array type string."""
    type_str = type_str.rstrip("?")
    # Split on all non-identifier characters
    tokens = re.split(r"[<>,\[\]\s\.\*\(\)]+", type_str)
    return {
        t for t in tokens
        if t and re.match(r"^[A-Z]\w*$", t) and t not in _PRIMITIVES
    }


def _iter_method_bodies(body: str):
    """Yield the inner content of each method body (skips property bodies and nested types)."""
    i = 0
    n = len(body)
    seg_start = 0
    while i < n:
        c = body[i]
        if c == "{":
            sig = body[seg_start:i].strip()
            close = _close_brace(body, i)
            inner = body[i + 1 : close]
            if sig and not _NESTED_TYPE.search(sig) and not _PROP_INNER.search(inner):
                yield inner
            seg_start = close + 1
            i = close + 1
        elif c == ";":
            seg_start = i + 1
            i += 1
        else:
            i += 1


_BODY_NEW_RE    = re.compile(r'\bnew\s+([A-Z]\w*(?:<[^>]+>)?)\s*[(<\[]')
_BODY_LOCAL_RE  = re.compile(r'(?<![.\w])([A-Z]\w*(?:<[^>]+>)?(?:\[\])?)\s+[a-z_]\w+\s*[=;,\)]')
_BODY_STATIC_RE = re.compile(r'(?<![.\w])([A-Z]\w+)\.(?=[A-Za-z_])')


def _scan_body_types(method_body: str) -> list[str]:
    """Extract type names used in a method body (new exprs, local vars, static access)."""
    types: list[str] = []
    for m in _BODY_NEW_RE.finditer(method_body):
        types.append(m.group(1))
    for m in _BODY_LOCAL_RE.finditer(method_body):
        types.append(m.group(1))
    for m in _BODY_STATIC_RE.finditer(method_body):
        types.append(m.group(1))
    return types


def _collect_newed_types(body: str) -> set[str]:
    """Types directly instantiated with `new` in method bodies or field initializers."""
    newed: set[str] = set()
    for method_body in _iter_method_bodies(body):
        for m in _BODY_NEW_RE.finditer(method_body):
            for tn in _extract_type_names(m.group(1)):
                newed.add(tn)
    for stmt in _flatten(body):
        if stmt.endswith(";") and " new " in stmt:
            for m in _BODY_NEW_RE.finditer(stmt):
                for tn in _extract_type_names(m.group(1)):
                    newed.add(tn)
    return newed


def _extract_member_types(body: str, name: str) -> tuple[list[tuple[str, bool]], list[str]]:
    """
    Returns (field_prop_items, method_types).
    field_prop_items: (type_str, is_public) from fields and properties
    method_types: raw type strings from method signatures and method bodies
    """
    base = name.split("<")[0]
    field_prop: list[tuple[str, bool]] = []
    method: list[str] = []

    for stmt in _flatten(body):
        stmt_clean = _ATTR_PREFIX.sub("", stmt).strip()
        if not stmt_clean:
            continue

        if "{ get/set }" in stmt_clean:
            m = _PROP_RE.match(stmt_clean)
            if m:
                field_prop.append((m.group("type"), _has(m.group("mods"), "public")))

        elif "(" in stmt_clean:
            m = _METHOD_RE.match(stmt_clean)
            if m and m.group("name") != base:
                method.append(m.group("ret"))
                raw_params = m.group("params")
                for param in raw_params.split(","):
                    param = re.sub(r"^(?:out|ref|in|params)\s+", "", param.strip())
                    parts = param.split()
                    if parts:
                        method.append(parts[0])

        elif stmt_clean.endswith(";"):
            m = _FIELD_RE.match(stmt_clean)
            if m:
                field_prop.append((m.group("type"), _has(m.group("mods"), "public")))

    for method_body in _iter_method_bodies(body):
        method.extend(_scan_body_types(method_body))

    return field_prop, method


def _build_uses_rels(
    decls: list[dict],
    known_types: set[str],
    inherit_rels_by_left: dict[str, set[str]],
) -> tuple[list[str], list[str]]:
    """Build relationship lines for known project types used in members.

    Returns (compose_rels, other_rels):
      compose_rels: *--> lines only — strong ownership, shown in base diagram too.
      other_rels:   -->, ..> lines — shown only in full diagram.

    Composition (*-->): newed in code OR public field.
    Association (-->):  private field, not newed.
    Dependency  (..>):  type appears only in method signatures or bodies.
    """
    compose_rels: list[str] = []
    other_rels: list[str] = []

    for d in decls:
        if d["kind"] not in ("class", "struct"):
            continue

        left = d["name"].split("<")[0]
        already = inherit_rels_by_left.get(left, set())

        fp_items, mt_types = _extract_member_types(d["body"], d["name"])
        newed_types = _collect_newed_types(d["body"])

        field_info: dict[str, dict[str, bool]] = {}
        for type_str, is_pub in fp_items:
            is_coll = _is_collection_type(type_str)
            for tn in _extract_type_names(type_str):
                if tn in known_types and tn != left and tn not in already:
                    if tn not in field_info:
                        field_info[tn] = {"is_coll": False, "is_public": False}
                    fi = field_info[tn]
                    fi["is_coll"] = fi["is_coll"] or is_coll
                    fi["is_public"] = fi["is_public"] or is_pub

        dep_set: set[str] = set()
        for t in mt_types:
            for tn in _extract_type_names(t):
                if tn in known_types and tn != left and tn not in already and tn not in field_info:
                    dep_set.add(tn)

        for tn in sorted(field_info):
            fi = field_info[tn]
            mult = ' "0..*"' if fi["is_coll"] else ""
            if tn in newed_types or fi["is_public"]:
                compose_rels.append(f"{left} *-->{mult} {tn}")
            else:
                other_rels.append(f"{left} -->{mult} {tn}")
        for tn in sorted(dep_set):
            other_rels.append(f"{left} ..> {tn}")

    return compose_rels, other_rels


# ── PlantUML generation ───────────────────────────────────────────────────────

def _gen_enum(name: str, body: str, lines: list[str]):
    body_clean = re.sub(r"\[[^\]]*\]", "", body)
    body_clean = re.sub(r"=\s*[^\n,]+", "", body_clean)
    values = [
        v.strip()
        for v in re.split(r"[,\n]", body_clean)
        if v.strip() and re.match(r"^\w+$", v.strip())
    ]
    lines.append(f"enum {name} <<enum>> {{")
    for v in values:
        lines.append(f"  {v}")
    lines.append("}")


def _gen_interface(name: str, body: str, lines: list[str]):
    lines.append(f"interface {name} <<interface>> {{")
    for stmt in _flatten(body):
        stmt = _ATTR_PREFIX.sub("", stmt).strip()
        stmt = re.sub(r"\s*\{\}$", "", stmt)
        stmt = re.sub(r"\s*\{ get/set \}$", "", stmt)
        stmt = re.sub(r"^public\s+", "", stmt)
        if not stmt:
            continue
        # Method
        m = re.match(r"([\w<>?,\[\]\.]+)\s+(\w+)\s*(?:<[^>]+>)?\s*\(([^)]*)\)", stmt)
        if m:
            lines.append(f"  + {m.group(2)}({_simplify_params(m.group(3))}) : {m.group(1)}")
            continue
        # Property
        m = re.match(r"([\w<>?,\[\]\.]+)\s+(\w+)\s*\{", stmt)
        if m:
            lines.append(f"  + {m.group(2)} : {m.group(1)}")
    lines.append("}")


def _class_stereotype(mods: str, base_class: str | None, kind: str) -> str:
    if kind == "struct":
        return "<<struct>>"
    if _has(mods, "abstract"):
        return "<<abstract>>"
    if _has(mods, "static"):
        return "<<static>>"
    return ""


# ── Namespace resolution ──────────────────────────────────────────────────────

_NAMESPACE_RE = re.compile(r"\bnamespace\s+([\w.]+)")
_USING_RE = re.compile(r"^\s*(?:global\s+)?using\s+([\w.]+)\s*;", re.MULTILINE)


def _parse_namespace(src: str) -> str | None:
    ns_m = _NAMESPACE_RE.search(src)
    return ns_m.group(1) if ns_m else None


def _collect_type_namespaces(cs_files: list[Path]) -> dict[str, set[str | None]]:
    """Simple name -> namespace(s) declaring it, for every project type. A
    name maps to several namespaces when unrelated namespaces reuse it."""
    type_namespaces: dict[str, set[str | None]] = {}
    for cs in cs_files:
        try:
            raw = cs.read_text(encoding="utf-8", errors="replace")
            src = _strip_strings(_strip_comments(raw))
            namespace = _parse_namespace(src)
            for d in _find_type_decls(src):
                type_namespaces.setdefault(d["name"].split("<")[0], set()).add(namespace)
        except Exception:
            pass
    return type_namespaces


def _enclosing_namespaces(namespace: str | None) -> list[str | None]:
    """A.B.C -> [A.B.C, A.B, A, None]: every namespace whose types are
    visible without a using directive, closest first (None = global)."""
    chain: list[str | None] = []
    parts = namespace.split(".") if namespace else []
    while parts:
        chain.append(".".join(parts))
        parts.pop()
    chain.append(None)
    return chain


def _resolve_namespace(
    name: str,
    own_namespace: str | None,
    own_names: set[str],
    usings: set[str],
    type_namespaces: dict[str, set[str | None]],
) -> str | None:
    """Namespace a referenced type lives in, or None when it can't be
    determined (non-project type, or a simple name declared in several
    namespaces with nothing to disambiguate) — such types are drawn outside
    any namespace rather than guessed into one. Unlike Java imports, C#
    using directives name namespaces, not types, so non-project types can't
    be placed."""
    if name in own_names:
        return own_namespace
    candidates = type_namespaces.get(name, set())
    for namespace in _enclosing_namespaces(own_namespace):
        if namespace in candidates:
            return namespace
    used = candidates & usings
    if len(used) == 1:
        return next(iter(used))
    if len(candidates) == 1:
        return next(iter(candidates))
    return None


def _resolve_rel_namespaces(
    rel_lines: list[str],
    own_namespace: str | None,
    own_names: set[str],
    src: str,
    type_namespaces: dict[str, set[str | None]],
) -> dict[str, str | None]:
    """Namespace of every name at either end of a relation line."""
    usings = set(_USING_RE.findall(src))
    names = {end for line in rel_lines for end in relation_ends(line)}
    return {
        name: _resolve_namespace(name, own_namespace, own_names, usings, type_namespaces)
        for name in names
    }


# ── File diagram building ─────────────────────────────────────────────────────

StereotypeFn = Callable[[str, str | None, str], str]
UsesRelsFn = Callable[[list[dict], set[str], dict[str, set[str]]], tuple[list[str], list[str]]]


@dataclass(frozen=True)
class GeneratorRules:
    """What differs between the plain C# and the Unity generator.
    hidden_bases: base classes never drawn as an inheritance arrow."""
    class_stereotype: StereotypeFn
    build_uses_rels: UsesRelsFn
    hidden_bases: frozenset[str] = frozenset()


CSHARP_RULES = GeneratorRules(_class_stereotype, _build_uses_rels)


def _render_class(d: dict, stereotype: str) -> list[str]:
    stereo_str = f" {stereotype}" if stereotype else ""
    prefix = "abstract " if _has(d["mods"], "abstract") else ""
    fields, props, methods = _parse_members(d["body"], d["name"])
    members = [f"  {member}" for member in fields + props + methods]
    return [f"{prefix}class {d['name']}{stereo_str} {{"] + members + ["}"]


def _render_decls(decls: list[dict], class_stereotype: StereotypeFn) -> list[str]:
    inner_lines: list[str] = []
    for d in decls:
        if d["kind"] == "enum":
            _gen_enum(d["name"], d["body"], inner_lines)
        elif d["kind"] == "interface":
            _gen_interface(d["name"], d["body"], inner_lines)
        else:
            base_class, _ = _split_bases(d["bases"])
            inner_lines.extend(_render_class(d, class_stereotype(d["mods"], base_class, d["kind"])))
    return inner_lines


def _inheritance_rels(
    decls: list[dict],
    hidden_bases: frozenset[str],
) -> tuple[list[str], dict[str, set[str]]]:
    """Returns (relation lines, inherited/implemented names per declared type).
    A hidden base draws no arrow but still counts as inherited, so it is
    never reported again as a usage."""
    rels: list[str] = []
    inherit_by_left: dict[str, set[str]] = {}
    for d in decls:
        base_class, ifaces = _split_bases(d["bases"])
        # Left side: strip type params — PlantUML registers 'class Foo<T>' as 'Foo'
        # Quoting 'Foo<T>' creates a separate entity instead of referencing the declaration
        left = d["name"].split("<")[0]
        targets: set[str] = set()
        if base_class:
            t = _puml_name(base_class)
            if t not in hidden_bases:
                rels.append(f"{left} --|> {t}")
            targets.add(t)
        for iface in ifaces:
            t = _puml_name(iface)
            rels.append(f"{left} ..|> {t}")
            targets.add(t)
        inherit_by_left[left] = targets
    return rels, inherit_by_left


def build_file_diagram(
    cs_path: Path,
    type_namespaces: dict[str, set[str | None]],
    rules: GeneratorRules = CSHARP_RULES,
) -> FileDiagram | None:
    """type_namespaces maps every project type's simple name to the
    namespace(s) declaring it. Returns None when the file declares no type."""
    raw = cs_path.read_text(encoding="utf-8", errors="replace")
    src = _strip_strings(_strip_comments(raw))
    decls = _find_type_decls(src)
    if not decls:
        return None

    namespace = _parse_namespace(src)
    rels, inherit_by_left = _inheritance_rels(decls, rules.hidden_bases)
    compose_rels, other_rels = rules.build_uses_rels(decls, set(type_namespaces), inherit_by_left)
    decl_names = set(inherit_by_left)
    name_namespaces = _resolve_rel_namespaces(
        rels + compose_rels + other_rels, namespace, decl_names, src, type_namespaces,
    )
    return FileDiagram(
        stem=cs_path.stem,
        package=namespace,
        decl_names=decl_names,
        inner_lines=_render_decls(decls, rules.class_stereotype),
        rels=rels,
        compose_rels=compose_rels,
        other_rels=other_rels,
        name_packages=name_namespaces,
    )


# ── Entry point ───────────────────────────────────────────────────────────────

NAMESPACE_VIEWS_DIR = "Namespaces"


def _generate_one(
    cs_path: Path,
    rel: Path,
    out_base: Path,
    type_namespaces: dict[str, set[str | None]],
    rules: GeneratorRules,
    skinparam_lines: list[str],
) -> FileDiagram | None:
    """Build and write all diagram variants for one file; prints its result
    line. Returns None when skipped or failed."""
    try:
        fd = build_file_diagram(cs_path, type_namespaces, rules)
        if fd is None:
            print(f"  SKIP   {rel}  (no type declarations)")
            return None
        write_file_outputs(fd, FileOutputPaths.under(out_base, rel), skinparam_lines)
    except Exception as exc:
        print(f"  ERROR  {rel}  — {exc}")
        return None
    print(f"  OK     {rel}")
    return fd


def generate_all(
    src_root: Path,
    cs_files: list[Path],
    out_base: Path,
    type_namespaces: dict[str, set[str | None]],
    rules: GeneratorRules,
    skinparam_lines: list[str],
) -> None:
    """Write every per-file diagram, then the namespace views built from them."""
    file_diagrams: list[FileDiagram] = []
    for cs in cs_files:
        fd = _generate_one(cs, cs.relative_to(src_root), out_base, type_namespaces, rules, skinparam_lines)
        if fd is not None:
            file_diagrams.append(fd)
    print(f"\nDone: {len(file_diagrams)} generated, {len(cs_files) - len(file_diagrams)} skipped or failed.")

    namespace_count = generate_package_views(file_diagrams, out_base, NAMESPACE_VIEWS_DIR, skinparam_lines)
    print(f"Wrote {namespace_count} namespace diagrams + overview + project views to {out_base / NAMESPACE_VIEWS_DIR}(-Full)")


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: generate_class_diagramm.py <src_dir> [out_dir]")
        print("  src_dir  — directory to search recursively for .cs files")
        print("  out_dir  — output root (default: <src_dir>/Modelisation)")
        sys.exit(1)

    src_root = Path(sys.argv[1])
    out_base = Path(sys.argv[2]) if len(sys.argv) > 2 else src_root / "Modelisation"

    cs_files = sorted(src_root.rglob("*.cs"))
    print(f"Found {len(cs_files)} .cs files under {src_root}")

    type_namespaces = _collect_type_namespaces(cs_files)
    print(f"  {len(type_namespaces)} known project types for uses-detection")

    generate_all(src_root, cs_files, out_base, type_namespaces, CSHARP_RULES, _SKINPARAM_LINES)


if __name__ == "__main__":
    main()
