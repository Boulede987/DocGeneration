"""Java source-level parsing: string stripping, package and imports, and
locating type declarations with their extends/implements lists."""

import re
from dataclasses import dataclass

from docgen.clike.text_scan import close_brace, split_by_comma

PACKAGE_RE = re.compile(r"\bpackage\s+([\w.]+)\s*;")
# Package segments are lowercase by convention; the first capitalized
# segment starts the type path, so a nested-type import like
# 'a.b.Outer.Inner' resolves Inner to package 'a.b', not to 'a.b.Outer' —
# a class name used as a namespace crashes PlantUML.
IMPORT_RE = re.compile(
    r"^\s*import\s+(?!static\b)((?:[a-z_]\w*\.)*[a-z_]\w*)\.(?:[A-Z]\w*\.)*([A-Z]\w*)\s*;",
    re.MULTILINE,
)
TYPE_DECL = re.compile(
    r"(?:@\w+(?:\([^)]*\))?\s+)*"                # leading annotations are not part of the header
    r"(?P<modifiers>"
    r"(?:(?:public|private|protected|static|final|"
    r"abstract|sealed|non-sealed|strictfp)\s+)*"
    r")"
    r"(?P<kind>class|interface|enum|record)\s+"
    r"(?P<name>\w+(?:\s*<[^>]+>)?)"
    r"(?P<record_params>\s*\([^)]*\))?"
    r"(?P<bases>(?:\s*(?:extends|implements|permits)\s+[^{]+?)*)"
    r"\s*\{",
    re.DOTALL,
)
_EXTENDS = re.compile(r"\bextends\s+(.*?)(?=\bimplements\b|\bpermits\b|$)", re.DOTALL)
_IMPLEMENTS = re.compile(r"\bimplements\s+(.*?)(?=\bpermits\b|$)", re.DOTALL)
_TEXT_BLOCK = re.compile(r'"""[\s\S]*?"""')
_STRING_LITERAL = re.compile(r'"(?:\\.|[^"\\])*"')
_CHAR_LITERAL = re.compile(r"'(?:\\.|[^'\\])+'")
EMPTY_STRING = '""'
EMPTY_CHAR = "''"
CLASS_KIND = "class"
INTERFACE_KIND = "interface"


@dataclass(frozen=True)
class TypeHeader:
    modifiers: str
    kind: str
    name: str
    base_class: str | None
    interfaces: list[str]
    record_params: str | None
    body: str


def strip_strings(source: str) -> str:
    """Literal contents may hold braces or keywords that would mislead the
    declaration scanner."""
    without_text_blocks = _TEXT_BLOCK.sub(EMPTY_STRING, source)
    without_strings = _STRING_LITERAL.sub(EMPTY_STRING, without_text_blocks)
    return _CHAR_LITERAL.sub(EMPTY_CHAR, without_strings)


def parse_package(source: str) -> str | None:
    match = PACKAGE_RE.search(source)
    return match.group(1) if match else None


def parse_imports(source: str) -> dict[str, str]:
    """Simple name -> package for each single-type import (wildcard and
    static imports name no single type, so they're skipped)."""
    return {match.group(2): match.group(1) for match in IMPORT_RE.finditer(source)}


def _bases_after(pattern: re.Pattern[str], raw: str) -> list[str]:
    match = pattern.search(raw)
    text = match.group(1).strip() if match else ""
    return split_by_comma(text) if text else []


def _supertypes(kind: str, raw_bases: str) -> tuple[str | None, list[str]]:
    """(base class, interfaces). 'permits' is discarded; an interface's
    'extends' list holds interfaces; enums and records have no visible
    superclass."""
    bases = raw_bases.strip()
    extends = _bases_after(_EXTENDS, bases)
    implements = _bases_after(_IMPLEMENTS, bases)
    if kind == CLASS_KIND:
        return (extends[0] if extends else None), implements
    if kind == INTERFACE_KIND:
        return None, extends + implements
    return None, implements


def find_type_headers(source: str) -> list[TypeHeader]:
    headers = []
    for match in TYPE_DECL.finditer(source):
        open_brace_index = match.end() - 1  # the pattern ends on the body's '{'
        close_brace_index = close_brace(source, open_brace_index)
        kind = match.group("kind")
        base_class, interfaces = _supertypes(kind, match.group("bases") or "")
        headers.append(TypeHeader(
            modifiers=match.group("modifiers").strip(),
            kind=kind,
            name=re.sub(r"\s+", "", match.group("name")),
            base_class=base_class,
            interfaces=interfaces,
            record_params=match.group("record_params"),
            body=source[open_brace_index + 1:close_brace_index],
        ))
    return headers
