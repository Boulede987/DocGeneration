"""Text scanning for C-like (brace-delimited) languages: comment stripping,
brace matching, depth-aware splitting, and flattening a type body into one
string per member declaration."""

import re

_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_LINE_COMMENT = re.compile(r"//[^\n]*")
BLOCK_OPEN = "{"
BLOCK_CLOSE = "}"
STATEMENT_END = ";"
LIST_SEPARATOR = ","
_ANY_OPENING_BRACKET = "([{"
_ANY_CLOSING_BRACKET = ")]}"
_TYPE_ARGUMENT_OPENING = "<("
_TYPE_ARGUMENT_CLOSING = ">)"
PROPERTY_PLACEHOLDER = " { get/set }"
BODY_PLACEHOLDER = " {}"


def strip_c_comments(source: str) -> str:
    return _LINE_COMMENT.sub("", _BLOCK_COMMENT.sub("", source))


def close_brace(text: str, open_index: int) -> int:
    """Index of the } matching the { at open_index (end of text if unmatched)."""
    depth = 0
    for index in range(open_index, len(text)):
        if text[index] == BLOCK_OPEN:
            depth += 1
        elif text[index] == BLOCK_CLOSE:
            depth -= 1
            if depth == 0:
                return index
    return len(text) - 1


def split_top_level(body: str, separator: str) -> tuple[str, str]:
    """Split at the first separator outside any (), [] or {}."""
    depth = 0
    for index, char in enumerate(body):
        if char in _ANY_OPENING_BRACKET:
            depth += 1
        elif char in _ANY_CLOSING_BRACKET:
            depth -= 1
        elif char == separator and depth == 0:
            return body[:index], body[index + 1:]
    return body, ""


def split_by_comma(raw: str) -> list[str]:
    """Split 'A, B<C,D>, E' by comma, ignoring commas inside <> and ()."""
    parts: list[str] = []
    depth = 0
    current: list[str] = []
    for char in raw:
        if char in _TYPE_ARGUMENT_OPENING:
            depth += 1
        elif char in _TYPE_ARGUMENT_CLOSING:
            depth -= 1
        elif char == LIST_SEPARATOR and depth == 0:
            parts.append("".join(current))
            current = []
            continue
        current.append(char)
    parts.append("".join(current))
    return [part.strip() for part in parts if part.strip()]


def _braced_statement(signature: str, inner: str, nested_type: re.Pattern[str],
                      property_inner: re.Pattern[str] | None) -> str | None:
    """The statement a braced block contributes; None for a nested type or
    a block with no signature."""
    if not signature or nested_type.search(signature):
        return None
    if property_inner is not None and property_inner.search(inner):
        return signature + PROPERTY_PLACEHOLDER
    return signature + BODY_PLACEHOLDER


def flatten(body: str, nested_type: re.Pattern[str], property_inner: re.Pattern[str] | None = None) -> list[str]:
    """One string per member declaration of a type body:
    - a braced block keeps its signature, the block collapsed to ' {}'
      (or ' { get/set }' when property_inner matches inside it);
      blocks whose signature declares a nested type are dropped;
    - a ';' ends a field or bodiless method declaration (kept with its ';').
    """
    statements: list[str | None] = []
    index = 0
    segment_start = 0
    while index < len(body):
        if body[index] == BLOCK_OPEN:
            close_index = close_brace(body, index)
            signature = body[segment_start:index].strip()
            statements.append(_braced_statement(signature, body[index + 1:close_index], nested_type, property_inner))
            index = close_index + 1
            segment_start = index
        elif body[index] == STATEMENT_END:
            segment = body[segment_start:index].strip()
            statements.append(segment + STATEMENT_END if segment else None)
            index += 1
            segment_start = index
        else:
            index += 1
    statements.append(body[segment_start:].strip() or None)
    return [statement for statement in statements if statement]
