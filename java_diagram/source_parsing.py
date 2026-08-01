"""Strip Java comments/strings and locate top-level type declarations
(class/interface/enum/record) with their extends/implements lists."""

import re

from .depth_utils import close_brace, split_bases_raw


def strip_comments(src: str) -> str:
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.DOTALL)
    src = re.sub(r"//[^\n]*", "", src)
    return src


def strip_strings(src: str) -> str:
    # Text blocks (triple-quoted, may span lines)
    src = re.sub(r'"""[\s\S]*?"""', '""', src)
    # Regular strings
    src = re.sub(r'"(?:\\.|[^"\\])*"', '""', src)
    # Char literals
    src = re.sub(r"'(?:\\.|[^'\\])+'", "''", src)
    return src


TYPE_DECL = re.compile(
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


def _split_java_bases(raw: str) -> tuple[list[str], list[str]]:
    """Split the combined 'extends X implements Y, Z permits W' tail into
    (extends_list, implements_list). 'permits' is discarded."""
    raw = raw.strip()
    extends_m = re.search(r"\bextends\s+(.*?)(?=\bimplements\b|\bpermits\b|$)", raw, re.DOTALL)
    implements_m = re.search(r"\bimplements\s+(.*?)(?=\bpermits\b|$)", raw, re.DOTALL)
    extends_raw = extends_m.group(1).strip() if extends_m else ""
    implements_raw = implements_m.group(1).strip() if implements_m else ""
    extends_list = split_bases_raw(extends_raw) if extends_raw else []
    implements_list = split_bases_raw(implements_raw) if implements_raw else []
    return extends_list, implements_list


def find_type_decls(src: str) -> list[dict]:
    results = []
    for m in TYPE_DECL.finditer(src):
        open_pos = m.end() - 1
        if src[open_pos] != "{":
            open_pos = src.rindex("{", m.start(), m.end())
        close_pos = close_brace(src, open_pos)
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
