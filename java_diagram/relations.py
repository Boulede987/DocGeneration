"""Detect composition/association/dependency relationships between known
project types, based on how each type is used as a field, method signature,
or local variable within another type's body."""

import re

from .depth_utils import close_brace
from .type_format import is_collection_type
from .members import ANNOT_PREFIX, FIELD_RE, METHOD_RE, NESTED_TYPE, flatten, has, parse_record_components

PRIMITIVES = frozenset({
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


def extract_type_names(type_str: str) -> set[str]:
    """Extract bare class names from a possibly generic/array type string."""
    type_str = type_str.rstrip("?")
    tokens = re.split(r"[<>,\[\]\s\.\*\(\)]+", type_str)
    return {
        t for t in tokens
        if t and re.match(r"^[A-Z]\w*$", t) and t not in PRIMITIVES
    }


def iter_method_bodies(body: str):
    """Yield the inner content of each method body (skips nested types)."""
    i = 0
    n = len(body)
    seg_start = 0
    while i < n:
        c = body[i]
        if c == "{":
            sig = body[seg_start:i].strip()
            close = close_brace(body, i)
            inner = body[i + 1: close]
            if sig and not NESTED_TYPE.search(sig):
                yield inner
            seg_start = close + 1
            i = close + 1
        elif c == ";":
            seg_start = i + 1
            i += 1
        else:
            i += 1


BODY_NEW_RE = re.compile(r'\bnew\s+([A-Z]\w*(?:<[^>]+>)?)\s*[(<\[]')
BODY_LOCAL_RE = re.compile(r'(?<![.\w])([A-Z]\w*(?:<[^>]+>)?(?:\[\])?)\s+[a-z_]\w+\s*[=;,\)]')
BODY_STATIC_RE = re.compile(r'(?<![.\w])([A-Z]\w+)\.(?=[A-Za-z_])')


def scan_body_types(method_body: str) -> list[str]:
    """Extract type names used in a method body (new exprs, local vars, static access)."""
    types: list[str] = []
    for m in BODY_NEW_RE.finditer(method_body):
        types.append(m.group(1))
    for m in BODY_LOCAL_RE.finditer(method_body):
        types.append(m.group(1))
    for m in BODY_STATIC_RE.finditer(method_body):
        types.append(m.group(1))
    return types


def collect_newed_types(body: str) -> set[str]:
    """Types directly instantiated with `new` in method bodies or field initializers."""
    newed: set[str] = set()
    for method_body in iter_method_bodies(body):
        for m in BODY_NEW_RE.finditer(method_body):
            for tn in extract_type_names(m.group(1)):
                newed.add(tn)
    for stmt in flatten(body):
        if stmt.endswith(";") and " new " in stmt:
            for m in BODY_NEW_RE.finditer(stmt):
                for tn in extract_type_names(m.group(1)):
                    newed.add(tn)
    return newed


def extract_member_types(body: str, name: str) -> tuple[list[tuple[str, bool]], list[str]]:
    """
    Returns (field_items, method_types).
    field_items: (type_str, is_public) from fields
    method_types: raw type strings from method signatures and method bodies
    """
    base = name.split("<")[0]
    field_items: list[tuple[str, bool]] = []
    method: list[str] = []

    for stmt in flatten(body):
        stmt_clean = ANNOT_PREFIX.sub("", stmt).strip()
        if not stmt_clean:
            continue

        if "(" in stmt_clean:
            m = METHOD_RE.match(stmt_clean)
            if m and m.group("name") != base:
                method.append(m.group("ret"))
                for param in m.group("params").split(","):
                    param = re.sub(r"^(?:final)\s+", "", param.strip())
                    parts = param.split()
                    if parts:
                        method.append(parts[0])

        elif stmt_clean.endswith(";"):
            m = FIELD_RE.match(stmt_clean)
            if m:
                field_items.append((m.group("type"), has(m.group("mods"), "public")))

    for method_body in iter_method_bodies(body):
        method.extend(scan_body_types(method_body))

    return field_items, method


def build_uses_rels(
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

        fp_items, mt_types = extract_member_types(d["body"], d["name"])
        newed_types = collect_newed_types(d["body"])

        # Record components behave like public fields (accessed via public accessor)
        for component_name, component_type in parse_record_components(d.get("record_params")):
            fp_items.append((component_type, True))

        field_info: dict[str, dict[str, bool]] = {}
        for type_str, is_pub in fp_items:
            is_coll = is_collection_type(type_str)
            for tn in extract_type_names(type_str):
                if tn in known_types and tn != left and tn not in already:
                    if tn not in field_info:
                        field_info[tn] = {"is_coll": False, "is_public": False}
                    fi = field_info[tn]
                    fi["is_coll"] = fi["is_coll"] or is_coll
                    fi["is_public"] = fi["is_public"] or is_pub

        dep_set: set[str] = set()
        for t in mt_types:
            for tn in extract_type_names(t):
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
