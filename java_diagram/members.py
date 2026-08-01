"""Java member (field/method) extraction from a type body: modifiers,
visibility, and flattening braces/semicolons into individual declarations."""

import re

from .depth_utils import split_bases_raw, close_brace
from .type_format import uml_type

MODS_PAT = (
    r"(?P<mods>"
    r"(?:(?:public|private|protected|static|final|abstract|synchronized|"
    r"native|transient|volatile|strictfp|default)\s+)+"
    r")"
)

VIS_RULES = [
    ("private", "-"),
    ("protected", "#"),
    ("public", "+"),
]


def vis(mods: str) -> str:
    for key, sym in VIS_RULES:
        if key in mods:
            return sym
    return "~"  # package-private


def has(mods: str, *flags) -> bool:
    words = set(mods.split())
    return any(f in words for f in flags)


# ── Member flattener ──────────────────────────────────────────────────────────

NESTED_TYPE = re.compile(r"\b(?:class|interface|enum|record)\b")


def flatten(body: str) -> list[str]:
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
            close = close_brace(body, i)

            if sig:
                if NESTED_TYPE.search(sig):
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

ANNOT_PREFIX = re.compile(r"^(?:\s*@\w+(?:\([^)]*\))?\s*)+")
METHOD_RE = re.compile(
    MODS_PAT
    + r"(?:<[^>]+>\s+)?"                           # optional method-level type params
    + r"(?P<ret>[\w<>\[\],\.\? ]+(?:\[\])*)\s+"
    + r"(?P<name>\w+)\s*"
    + r"\((?P<params>[^)]*)\)",
)
FIELD_RE = re.compile(
    MODS_PAT
    + r"(?P<type>[\w<>\[\],\.\? ]+(?:\[\])*)\s+"
    + r"(?P<name>\w+)",
)


def simplify_params(raw: str) -> str:
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
    stmt = ANNOT_PREFIX.sub("", stmt).strip()
    if not stmt:
        return None

    if "(" in stmt:
        m = METHOD_RE.match(stmt)
        if m:
            name = m.group("name")
            if name == class_base:
                return None  # constructor
            return "method", {
                "mods": m.group("mods").strip(),
                "ret": m.group("ret"),
                "name": name,
                "params": simplify_params(m.group("params")),
                "params_raw": m.group("params"),
            }

    if stmt.endswith(";"):
        m = FIELD_RE.match(stmt)
        if m:
            return "field", {
                "mods": m.group("mods").strip(),
                "type": m.group("type"),
                "name": m.group("name"),
            }

    return None


def parse_members(body: str, name: str):
    """Return (fields, methods) as lists of PlantUML strings."""
    base = name.split("<")[0]
    fields, methods = [], []

    for stmt in flatten(body):
        result = _parse_member(stmt, base)
        if result is None:
            continue
        kind, info = result
        mods = info["mods"]
        member_vis = vis(mods)

        extra = []
        if has(mods, "static"):
            extra.append("{static}")
        if has(mods, "abstract"):
            extra.append("{abstract}")
        prefix = (" ".join(extra) + " ") if extra else ""

        if kind == "field":
            fields.append(f"{member_vis} {prefix}{info['name']} : {uml_type(info['type'])}")
        elif kind == "method":
            params = info["params"]
            ret = info["ret"]
            ret_suffix = "" if ret == "void" else f" : {ret}"
            methods.append(
                f"{member_vis} {prefix}{info['name']}({params}){ret_suffix}"
            )

    return fields, methods


def parse_record_components(raw: str | None) -> list[tuple[str, str]]:
    """Parse 'record Point(int x, int y)' header into [(name, type), ...]."""
    if not raw:
        return []
    raw = raw.strip()
    if raw.startswith("(") and raw.endswith(")"):
        raw = raw[1:-1]
    fields = []
    for p in split_bases_raw(raw):
        p = ANNOT_PREFIX.sub("", p).strip()
        p = p.replace("...", "[]")
        tokens = p.rsplit(None, 1)
        if len(tokens) == 2:
            component_type, component_name = tokens
            fields.append((component_name, component_type))
    return fields
