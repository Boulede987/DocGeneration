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

# ── Modifier keywords ─────────────────────────────────────────────────────────

_MODS_PAT = (
    r"(?P<mods>"
    r"(?:(?:public|private|protected|static|final|abstract|synchronized|"
    r"native|transient|volatile|strictfp|default)\s+)+"
    r")"
)

_VIS_RULES = [
    ("private", "-"),
    ("protected", "#"),
    ("public", "+"),
]


def _vis(mods: str) -> str:
    for key, sym in _VIS_RULES:
        if key in mods:
            return sym
    return "~"  # package-private


def _has(mods: str, *flags) -> bool:
    words = set(mods.split())
    return any(f in words for f in flags)


# ── Source pre-processing ─────────────────────────────────────────────────────

def _strip_comments(src: str) -> str:
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.DOTALL)
    src = re.sub(r"//[^\n]*", "", src)
    return src


def _strip_strings(src: str) -> str:
    # Text blocks (triple-quoted, may span lines)
    src = re.sub(r'"""[\s\S]*?"""', '""', src)
    # Regular strings
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


def _split_top_level(body: str, sep: str) -> tuple[str, str]:
    """Split body at the first occurrence of sep that is at bracket depth 0."""
    depth = 0
    for i, c in enumerate(body):
        if c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
        elif c == sep and depth == 0:
            return body[:i], body[i + 1:]
    return body, ""


# ── Type-declaration finder ───────────────────────────────────────────────────

_TYPE_DECL = re.compile(
    r"(?:@\w+(?:\([^)]*\))?\s+)*"                # annotations (e.g. @Deprecated)
    r"(?P<mods>"
    r"(?:(?:public|private|protected|static|final|"
    r"abstract|sealed|non-sealed|strictfp)\s+)*"
    r")"
    r"(?P<kind>class|interface|enum|record)\s+"
    r"(?P<name>\w+(?:\s*<[^>]+>)?)"              # name with optional <T>
    r"(?P<recparams>\s*\([^)]*\))?"              # record components
    r"(?P<bases>(?:\s*(?:extends|implements|permits)\s+[^{]+?)*)"
    r"\s*\{",
    re.DOTALL,
)


def _split_bases_raw(raw: str) -> list[str]:
    """Split 'A, B<C,D>, E' by comma respecting <> and () depth."""
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


def _split_java_bases(raw: str) -> tuple[list[str], list[str]]:
    """Split the combined 'extends X implements Y, Z permits W' tail into
    (extends_list, implements_list). 'permits' is discarded."""
    raw = raw.strip()
    extends_m = re.search(r"\bextends\s+(.*?)(?=\bimplements\b|\bpermits\b|$)", raw, re.DOTALL)
    implements_m = re.search(r"\bimplements\s+(.*?)(?=\bpermits\b|$)", raw, re.DOTALL)
    extends_raw = extends_m.group(1).strip() if extends_m else ""
    implements_raw = implements_m.group(1).strip() if implements_m else ""
    extends_list = _split_bases_raw(extends_raw) if extends_raw else []
    implements_list = _split_bases_raw(implements_raw) if implements_raw else []
    return extends_list, implements_list


def _find_type_decls(src: str) -> list[dict]:
    results = []
    for m in _TYPE_DECL.finditer(src):
        open_pos = m.end() - 1
        if src[open_pos] != "{":
            open_pos = src.rindex("{", m.start(), m.end())
        close_pos = _close_brace(src, open_pos)
        body = src[open_pos + 1: close_pos]

        name = re.sub(r"\s+", "", m.group("name"))
        kind = m.group("kind")
        extends_list, implements_list = _split_java_bases(m.group("bases") or "")

        if kind == "class":
            base_class = extends_list[0] if extends_list else None
            interfaces = implements_list
        elif kind == "interface":
            base_class = None
            interfaces = extends_list + implements_list
        else:  # enum, record — no user-visible superclass
            base_class = None
            interfaces = implements_list

        results.append(
            {
                "mods": m.group("mods").strip(),
                "kind": kind,
                "name": name,
                "base_class": base_class,
                "interfaces": interfaces,
                "record_params": m.group("recparams"),
                "body": body,
            }
        )
    return results


# ── Member flattener ──────────────────────────────────────────────────────────

_NESTED_TYPE = re.compile(r"\b(?:class|interface|enum|record)\b")


def _flatten(body: str) -> list[str]:
    """
    Walk a type body and collect member declarations as strings.

    Rules:
    - Hit { at depth 0 → collapse to placeholder (keeps signature), skip nested types.
    - Hit ; at depth 0 → field or abstract/interface method.
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

            if sig:
                if _NESTED_TYPE.search(sig):
                    pass  # skip nested type declaration
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

_ANNOT_PREFIX = re.compile(r"^(?:\s*@\w+(?:\([^)]*\))?\s*)+")
_METHOD_RE = re.compile(
    _MODS_PAT
    + r"(?:<[^>]+>\s+)?"                          # optional method-level type params
    + r"(?P<ret>[\w<>\[\],\.\? ]+(?:\[\])*)\s+"
    + r"(?P<name>\w+)\s*"
    + r"\((?P<params>[^)]*)\)",
)
_FIELD_RE = re.compile(
    _MODS_PAT
    + r"(?P<type>[\w<>\[\],\.\? ]+(?:\[\])*)\s+"
    + r"(?P<name>\w+)",
)


def _simplify_params(raw: str) -> str:
    if not raw.strip():
        return ""
    out = []
    for p in raw.split(","):
        p = re.sub(r"^(?:final)\s+", "", p.strip())
        p = p.replace("...", "[]")
        parts = p.split()
        if parts:
            out.append(parts[0])
    return ", ".join(out)


def _parse_member(stmt: str, class_base: str):
    """Return (kind, info_dict) or None. Java has fields and methods only —
    no C#-style auto-properties."""
    stmt = _ANNOT_PREFIX.sub("", stmt).strip()
    if not stmt:
        return None

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
    """Return (fields, methods) as lists of PlantUML strings."""
    base = name.split("<")[0]
    fields, methods = [], []

    for stmt in _flatten(body):
        result = _parse_member(stmt, base)
        if result is None:
            continue
        kind, info = result
        mods = info["mods"]
        vis = _vis(mods)

        extra = []
        if _has(mods, "static"):
            extra.append("{static}")
        if _has(mods, "abstract"):
            extra.append("{abstract}")
        prefix = (" ".join(extra) + " ") if extra else ""

        if kind == "field":
            fields.append(f"{vis} {prefix}{info['name']} : {_uml_type(info['type'])}")
        elif kind == "method":
            params = info["params"]
            ret = info["ret"]
            ret_suffix = "" if ret == "void" else f" : {ret}"
            methods.append(
                f"{vis} {prefix}{info['name']}({params}){ret_suffix}"
            )

    return fields, methods


def _parse_record_components(raw: str | None) -> list[tuple[str, str]]:
    """Parse 'record Point(int x, int y)' header into [(name, type), ...]."""
    if not raw:
        return []
    raw = raw.strip()
    if raw.startswith("(") and raw.endswith(")"):
        raw = raw[1:-1]
    fields = []
    for p in _split_bases_raw(raw):
        p = _ANNOT_PREFIX.sub("", p).strip()
        p = p.replace("...", "[]")
        tokens = p.rsplit(None, 1)
        if len(tokens) == 2:
            component_type, component_name = tokens
            fields.append((component_name, component_type))
    return fields


# ── Relationship helpers ──────────────────────────────────────────────────────

def _puml_name(name: str) -> str:
    """Strip generic parameters from a type name for relationship lines.
    PlantUML registers 'class Foo<T>' as 'Foo', so all cross-file references
    must use the bare name — otherwise !include linking breaks."""
    return name.split("<")[0]


# ── Uses/composition detection ────────────────────────────────────────────────

_COLLECTION_WRAPPERS = frozenset({
    "List", "ArrayList", "LinkedList", "Vector", "Stack",
    "Set", "HashSet", "LinkedHashSet", "TreeSet", "SortedSet", "NavigableSet",
    "Collection", "Queue", "Deque", "ArrayDeque", "PriorityQueue",
    "BlockingQueue", "ConcurrentLinkedQueue", "ConcurrentLinkedDeque",
    "CopyOnWriteArrayList", "CopyOnWriteArraySet",
})


def _is_collection_type(type_str: str) -> bool:
    t = type_str.rstrip("?")
    if t.endswith("[]"):
        return True
    return t.split("<")[0] in _COLLECTION_WRAPPERS


def _uml_type(type_str: str) -> str:
    """Convert Java collection types to UML multiplicity notation."""
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
    "  BackgroundColor<<record>> #FCF3CF",
    "  BorderColor<<record>> #B7950B",
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
    "void", "boolean", "int", "byte", "short", "long", "float", "double", "char",
    "Object", "String", "var",
    # single-letter/common generic params
    "T", "U", "V", "K", "E", "R", "S",
    # common JDK containers and types (not project classes)
    "List", "ArrayList", "LinkedList", "Vector", "Stack",
    "Map", "HashMap", "TreeMap", "LinkedHashMap", "ConcurrentHashMap",
    "Set", "HashSet", "TreeSet", "LinkedHashSet",
    "Queue", "Deque", "ArrayDeque", "PriorityQueue",
    "Collection", "Collections", "Iterable", "Iterator", "Optional",
    "Stream", "IntStream", "LongStream", "DoubleStream", "Collectors",
    "Comparator", "Comparable", "Function", "BiFunction", "Consumer",
    "BiConsumer", "Supplier", "Predicate", "Runnable", "Callable", "Thread",
    "Exception", "RuntimeException", "IllegalArgumentException",
    "IllegalStateException", "IOException", "NullPointerException",
    "Objects", "Arrays", "Math", "StringBuilder", "StringBuffer",
    "Pattern", "Matcher", "Class", "Enum", "Record",
    "Number", "Integer", "Long", "Double", "Float", "Boolean", "Character",
    "Byte", "Short", "Void", "System",
    "Serializable", "Cloneable", "AutoCloseable", "Closeable",
    "Override", "Deprecated", "SuppressWarnings", "FunctionalInterface",
})


def _extract_type_names(type_str: str) -> set[str]:
    """Extract bare class names from a possibly generic/array type string."""
    type_str = type_str.rstrip("?")
    tokens = re.split(r"[<>,\[\]\s\.\*\(\)]+", type_str)
    return {
        t for t in tokens
        if t and re.match(r"^[A-Z]\w*$", t) and t not in _PRIMITIVES
    }


def _iter_method_bodies(body: str):
    """Yield the inner content of each method body (skips nested types)."""
    i = 0
    n = len(body)
    seg_start = 0
    while i < n:
        c = body[i]
        if c == "{":
            sig = body[seg_start:i].strip()
            close = _close_brace(body, i)
            inner = body[i + 1: close]
            if sig and not _NESTED_TYPE.search(sig):
                yield inner
            seg_start = close + 1
            i = close + 1
        elif c == ";":
            seg_start = i + 1
            i += 1
        else:
            i += 1


_BODY_NEW_RE = re.compile(r'\bnew\s+([A-Z]\w*(?:<[^>]+>)?)\s*[(<\[]')
_BODY_LOCAL_RE = re.compile(r'(?<![.\w])([A-Z]\w*(?:<[^>]+>)?(?:\[\])?)\s+[a-z_]\w+\s*[=;,\)]')
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
    Returns (field_items, method_types).
    field_items: (type_str, is_public) from fields
    method_types: raw type strings from method signatures and method bodies
    """
    base = name.split("<")[0]
    field_items: list[tuple[str, bool]] = []
    method: list[str] = []

    for stmt in _flatten(body):
        stmt_clean = _ANNOT_PREFIX.sub("", stmt).strip()
        if not stmt_clean:
            continue

        if "(" in stmt_clean:
            m = _METHOD_RE.match(stmt_clean)
            if m and m.group("name") != base:
                method.append(m.group("ret"))
                for param in m.group("params").split(","):
                    param = re.sub(r"^(?:final)\s+", "", param.strip())
                    parts = param.split()
                    if parts:
                        method.append(parts[0])

        elif stmt_clean.endswith(";"):
            m = _FIELD_RE.match(stmt_clean)
            if m:
                field_items.append((m.group("type"), _has(m.group("mods"), "public")))

    for method_body in _iter_method_bodies(body):
        method.extend(_scan_body_types(method_body))

    return field_items, method


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
        if d["kind"] not in ("class", "record"):
            continue

        left = d["name"].split("<")[0]
        already = inherit_rels_by_left.get(left, set())

        fp_items, mt_types = _extract_member_types(d["body"], d["name"])
        newed_types = _collect_newed_types(d["body"])

        # Record components behave like public fields (accessed via public accessor)
        for component_name, component_type in _parse_record_components(d.get("record_params")):
            fp_items.append((component_type, True))

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
    const_part, _rest = _split_top_level(body, ";")
    const_part = re.sub(r"@\w+(?:\([^)]*\))?", "", const_part)   # strip annotations
    const_part = re.sub(r"\([^()]*\)", "", const_part)           # strip ctor args
    const_part = re.sub(r"\{[^{}]*\}", "", const_part)           # strip anon bodies
    values = [
        v.strip()
        for v in const_part.split(",")
        if v.strip() and re.match(r"^\w+$", v.strip())
    ]
    lines.append(f"enum {name} <<enum>> {{")
    for v in values:
        lines.append(f"  {v}")
    lines.append("}")


def _gen_interface(name: str, body: str, lines: list[str]):
    lines.append(f"interface {name} <<interface>> {{")
    for stmt in _flatten(body):
        stmt = _ANNOT_PREFIX.sub("", stmt).strip()
        stmt = re.sub(r"\s*\{[^{}]*\}$", "", stmt)
        stmt = re.sub(r"^(?:(?:public|abstract|default|static|final)\s+)+", "", stmt)
        if not stmt:
            continue
        # Method
        m = re.match(r"([\w<>\[\],\.\? ]+)\s+(\w+)\s*(?:<[^>]+>)?\s*\(([^)]*)\)", stmt)
        if m:
            lines.append(f"  + {m.group(2)}({_simplify_params(m.group(3))}) : {m.group(1)}")
            continue
        # Constant field
        if stmt.endswith(";"):
            m = re.match(r"([\w<>\[\],\.\? ]+)\s+(\w+)", stmt)
            if m:
                lines.append(f"  + {{static}} {m.group(2)} : {m.group(1)}")
    lines.append("}")


def _class_stereotype(mods: str, kind: str) -> str:
    if kind == "record":
        return "<<record>>"
    if _has(mods, "abstract"):
        return "<<abstract>>"
    if _has(mods, "static"):
        return "<<static>>"
    return ""


def _assemble(
    stem: str,
    package: str | None,
    inner_lines: list[str],
    rels: list[str],
    extra_rels: list[str],
) -> tuple[list[str], list[str]]:
    """Returns (full_lines, body_lines).
    body_lines has no @startuml, skinparam, or @enduml — for use as fragment."""
    body: list[str] = []
    if package:
        body.append(f"namespace {package} {{")
    body.extend(inner_lines)
    body.append("")
    body.extend(rels)
    if extra_rels:
        body.extend(extra_rels)
    if package:
        body.append("}")

    full = [f"@startuml {stem}", ""] + _SKINPARAM_LINES + [""] + body + ["", "@enduml"]
    return full, body


def _write_file(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def generate_puml(
    java_path: Path,
    out_path: Path,
    frag_path: Path,
    full_out_path: Path | None = None,
    full_frag_path: Path | None = None,
    known_types: set[str] | None = None,
) -> bool:
    raw = java_path.read_text(encoding="utf-8", errors="replace")
    src = _strip_strings(_strip_comments(raw))

    pkg_m = re.search(r"\bpackage\s+([\w.]+)\s*;", src)
    package = pkg_m.group(1) if pkg_m else None

    decls = _find_type_decls(src)
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
            _gen_enum(name, body, inner_lines)
        elif kind == "interface":
            _gen_interface(name, body, inner_lines)
        elif kind == "record":
            stereo = _class_stereotype(mods, kind)
            inner_lines.append(f"class {name} {stereo} {{")
            for component_name, component_type in _parse_record_components(d["record_params"]):
                inner_lines.append(f"  + {component_name} : {_uml_type(component_type)}")
            fields, methods = _parse_members(body, name)
            for f in fields:
                inner_lines.append(f"  {f}")
            for m in methods:
                inner_lines.append(f"  {m}")
            inner_lines.append("}")
        else:
            stereo = _class_stereotype(mods, kind)
            stereo_str = f" {stereo}" if stereo else ""
            prefix = "abstract " if _has(mods, "abstract") else ""
            inner_lines.append(f"{prefix}class {name}{stereo_str} {{")
            fields, methods = _parse_members(body, name)
            for f in fields:
                inner_lines.append(f"  {f}")
            for m in methods:
                inner_lines.append(f"  {m}")
            inner_lines.append("}")

        # Left side: strip type params — PlantUML registers 'class Foo<T>' as 'Foo'
        left = name.split("<")[0]
        targets: set[str] = set()
        if base_class:
            t = _puml_name(base_class)
            rels.append(f"{left} --|> {t}")
            targets.add(t)
        for iface in ifaces:
            t = _puml_name(iface)
            rels.append(f"{left} ..|> {t}")
            targets.add(t)
        inherit_by_left[left] = targets

    # Base output (extends/implements only)
    base_all, base_body = _assemble(java_path.stem, package, inner_lines, rels, [])
    _write_file(out_path, base_all)
    _write_file(frag_path, base_body)

    # Full output (adds *-->, -->, ..> for project types used in members)
    if known_types is not None and full_out_path is not None and full_frag_path is not None:
        compose_rels, other_rels = _build_uses_rels(decls, known_types, inherit_by_left)

        if compose_rels:
            base_all, base_body = _assemble(java_path.stem, package, inner_lines, rels, compose_rels)
            _write_file(out_path, base_all)
            _write_file(frag_path, base_body)

        full_all, full_body = _assemble(java_path.stem, package, inner_lines, rels, compose_rels + other_rels)
        _write_file(full_out_path, full_all)
        _write_file(full_frag_path, full_body)

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
            src = _strip_strings(_strip_comments(raw))
            for d in _find_type_decls(src):
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
