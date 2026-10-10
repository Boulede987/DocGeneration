"""C# source-level parsing: string stripping, namespace and using
directives, and locating type declarations with their base lists."""

import re
from dataclasses import dataclass

from docgen.clike.text_scan import close_brace, split_by_comma

NAMESPACE_RE = re.compile(r"\bnamespace\s+([\w.]+)")
USING_RE = re.compile(r"^\s*(?:global\s+)?using\s+([\w.]+)\s*;", re.MULTILINE)
TYPE_DECL = re.compile(
    r"(?:(?:\[[^\]]*\]\s*)*)"                   # leading attributes are not part of the header
    r"(?P<modifiers>"
    r"(?:(?:public|private|protected|internal|"
    r"abstract|sealed|static|partial|new|readonly)\s+)+"
    r")"
    r"(?P<kind>class|interface|enum|struct)\s+"
    r"(?P<name>\w+(?:\s*<[^>]+>)?)"
    r"(?:\s*:\s*(?P<bases>[^{]+?))?"
    r"\s*\{",
    re.DOTALL,
)
_GENERIC_CONSTRAINTS = re.compile(r"\s+where\b.*$", re.DOTALL)
_INTERFACE_NAME = re.compile(r"^I[A-Z]")
_VERBATIM_STRING = re.compile(r'@"[^"]*(?:""[^"]*)*"')
_STRING_LITERAL = re.compile(r'"(?:\\.|[^"\\])*"')
_CHAR_LITERAL = re.compile(r"'(?:\\.|[^'\\])+'")
EMPTY_STRING = '""'
EMPTY_CHAR = "''"


@dataclass(frozen=True)
class TypeHeader:
    modifiers: str
    kind: str
    name: str
    base_class: str | None
    interfaces: list[str]
    body: str


def strip_strings(source: str) -> str:
    """Literal contents may hold braces or keywords that would mislead the
    declaration scanner. Verbatim strings go first: they may contain '""'."""
    without_verbatim = _VERBATIM_STRING.sub(EMPTY_STRING, source)
    without_strings = _STRING_LITERAL.sub(EMPTY_STRING, without_verbatim)
    return _CHAR_LITERAL.sub(EMPTY_CHAR, without_strings)


def parse_namespace(source: str) -> str | None:
    """The first namespace declared (block or file-scoped)."""
    match = NAMESPACE_RE.search(source)
    return match.group(1) if match else None


def parse_usings(source: str) -> set[str]:
    return set(USING_RE.findall(source))


def _supertypes(raw_bases: str) -> tuple[str | None, list[str]]:
    """C# doesn't mark which base is the class: a name like 'IFoo' is taken
    as an interface, the first other name as the base class."""
    base_class = None
    interfaces = []
    for base in split_by_comma(_GENERIC_CONSTRAINTS.sub("", raw_bases).strip()):
        if _INTERFACE_NAME.match(base) or base_class is not None:
            interfaces.append(base)
        else:
            base_class = base
    return base_class, interfaces


def find_type_headers(source: str) -> list[TypeHeader]:
    headers = []
    for match in TYPE_DECL.finditer(source):
        open_brace_index = match.end() - 1  # the pattern ends on the body's '{'
        close_brace_index = close_brace(source, open_brace_index)
        base_class, interfaces = _supertypes(match.group("bases") or "")
        headers.append(TypeHeader(
            modifiers=match.group("modifiers").strip(),
            kind=match.group("kind"),
            name=re.sub(r"\s+", "", match.group("name")),
            base_class=base_class,
            interfaces=interfaces,
            body=source[open_brace_index + 1:close_brace_index],
        ))
    return headers
