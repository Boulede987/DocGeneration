#!/usr/bin/env python3
"""
generate_puml.py
Reads every .cs file under jeu-pac-man/Assets/Scripts/ and writes:
  Modelisation/ClassDiagram/    — one .puml per file, inherits/implements only
  Modelisation/Fragments/       — fragment versions (no @startuml/@enduml)
  Modelisation/ClassDiagram-Full/ — same + --> (field/prop) and ..> (method-only) to known types
  Modelisation/Fragments-Full/    — fragment versions of the full diagrams
"""

import re
import sys
from pathlib import Path

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


def _assemble(
    stem: str,
    namespace: str | None,
    inner_lines: list[str],
    rels: list[str],
    extra_rels: list[str],
) -> tuple[list[str], list[str]]:
    """Returns (full_lines, body_lines).
    body_lines has no @startuml, skinparam, or @enduml — for use as fragment."""
    body: list[str] = []
    if namespace:
        body.append(f"namespace {namespace} {{")
    body.extend(inner_lines)
    body.append("")
    body.extend(rels)
    if extra_rels:
        body.extend(extra_rels)
    if namespace:
        body.append("}")

    full = [f"@startuml {stem}", ""] + _SKINPARAM_LINES + [""] + body + ["", "@enduml"]
    return full, body


def generate_puml(
    cs_path: Path,
    out_path: Path,
    frag_path: Path,
    full_out_path: Path | None = None,
    full_frag_path: Path | None = None,
    known_types: set[str] | None = None,
) -> bool:
    raw = cs_path.read_text(encoding="utf-8", errors="replace")
    src = _strip_strings(_strip_comments(raw))

    ns_m = re.search(r"\bnamespace\s+([\w.]+)", src)
    namespace = ns_m.group(1) if ns_m else None

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
        base_class, ifaces = _split_bases(d["bases"])

        if kind == "enum":
            _gen_enum(name, body, inner_lines)
        elif kind == "interface":
            _gen_interface(name, body, inner_lines)
        else:
            stereo = _class_stereotype(mods, base_class, kind)
            stereo_str = f" {stereo}" if stereo else ""
            prefix = "abstract " if _has(mods, "abstract") else ""
            inner_lines.append(f"{prefix}class {name}{stereo_str} {{")
            fields, props, methods = _parse_members(body, name)
            for f in fields:
                inner_lines.append(f"  {f}")
            for p in props:
                inner_lines.append(f"  {p}")
            for m in methods:
                inner_lines.append(f"  {m}")
            inner_lines.append("}")

        # Left side: strip type params — PlantUML registers 'class Foo<T>' as 'Foo'
        # Quoting 'Foo<T>' creates a separate entity instead of referencing the declaration
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

    # Base output (inherits/implements only)
    base_all, base_body = _assemble(cs_path.stem, namespace, inner_lines, rels, [])

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(base_all), encoding="utf-8")
    frag_path.parent.mkdir(parents=True, exist_ok=True)
    frag_path.write_text("\n".join(base_body), encoding="utf-8")

    # Full output (adds *-->, o-->, -->, ..> for project types used in members)
    if known_types is not None and full_out_path is not None and full_frag_path is not None:
        compose_rels, other_rels = _build_uses_rels(decls, known_types, inherit_by_left)

        # Base diagram also gets composition (*-->) — strong structural relation
        if compose_rels:
            base_all, base_body = _assemble(cs_path.stem, namespace, inner_lines, rels, compose_rels)
            out_path.write_text("\n".join(base_all), encoding="utf-8")
            frag_path.write_text("\n".join(base_body), encoding="utf-8")

        full_all, full_body = _assemble(cs_path.stem, namespace, inner_lines, rels, compose_rels + other_rels)

        full_out_path.parent.mkdir(parents=True, exist_ok=True)
        full_out_path.write_text("\n".join(full_all), encoding="utf-8")
        full_frag_path.parent.mkdir(parents=True, exist_ok=True)
        full_frag_path.write_text("\n".join(full_body), encoding="utf-8")

    return True


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: generate_puml.py <src_dir> [out_dir]")
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

    # First pass: collect all declared type names
    known_types: set[str] = set()
    for cs in cs_files:
        try:
            raw = cs.read_text(encoding="utf-8", errors="replace")
            src = _strip_strings(_strip_comments(raw))
            for d in _find_type_decls(src):
                known_types.add(d["name"].split("<")[0])
        except Exception:
            pass
    print(f"  {len(known_types)} known project types for uses-detection")

    ok = skipped = errors = 0
    for cs in cs_files:
        rel       = cs.relative_to(src_root)
        out       = out_root       / rel.with_suffix(".puml")
        frag      = frag_root      / rel.with_suffix(".puml")
        full_out  = full_out_root  / rel.with_suffix(".puml")
        full_frag = full_frag_root / rel.with_suffix(".puml")
        try:
            if generate_puml(cs, out, frag, full_out, full_frag, known_types):
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
