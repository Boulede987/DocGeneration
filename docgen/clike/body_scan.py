"""Find the type texts a C-like type body mentions inside its method bodies:
instantiations, local variable types, static member access."""

import re
from typing import Iterable, Iterator

from .text_scan import BLOCK_OPEN, STATEMENT_END, close_brace

_NEW_EXPRESSION = re.compile(r"\bnew\s+([A-Z]\w*(?:<[^>]+>)?)\s*[(<\[]")
_LOCAL_VARIABLE = re.compile(r"(?<![.\w])([A-Z]\w*(?:<[^>]+>)?(?:\[\])?)\s+[a-z_]\w+\s*[=;,\)]")
_STATIC_ACCESS = re.compile(r"(?<![.\w])([A-Z]\w+)\.(?=[A-Za-z_])")
_FIELD_INITIALIZER_NEW = " new "


def _is_method_block(signature: str, inner: str, nested_type: re.Pattern[str],
                     property_inner: re.Pattern[str] | None) -> bool:
    if not signature or nested_type.search(signature):
        return False
    return property_inner is None or property_inner.search(inner) is None


def iter_method_bodies(
    body: str,
    nested_type: re.Pattern[str],
    property_inner: re.Pattern[str] | None = None,
) -> Iterator[str]:
    """Inner text of each braced member block, skipping nested types and,
    when property_inner is given, property accessor blocks."""
    index = 0
    segment_start = 0
    while index < len(body):
        if body[index] == BLOCK_OPEN:
            close_index = close_brace(body, index)
            inner = body[index + 1:close_index]
            if _is_method_block(body[segment_start:index].strip(), inner, nested_type, property_inner):
                yield inner
            index = close_index + 1
            segment_start = index
        elif body[index] == STATEMENT_END:
            index += 1
            segment_start = index
        else:
            index += 1


def scan_body_types(method_body: str) -> list[str]:
    """Type texts used in a method body: new expressions, local variable
    declarations, then static member access."""
    patterns = (_NEW_EXPRESSION, _LOCAL_VARIABLE, _STATIC_ACCESS)
    return [match.group(1) for pattern in patterns for match in pattern.finditer(method_body)]


def instantiated_type_texts(method_bodies: Iterable[str], statements: Iterable[str]) -> list[str]:
    """Type texts of 'new' expressions in method bodies and in field
    initializers (statements from flatten())."""
    texts = [match.group(1) for body in method_bodies for match in _NEW_EXPRESSION.finditer(body)]
    for statement in statements:
        if statement.endswith(STATEMENT_END) and _FIELD_INITIALIZER_NEW in statement:
            texts.extend(match.group(1) for match in _NEW_EXPRESSION.finditer(statement))
    return texts
