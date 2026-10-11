"""C# type bodies -> members, enum values, and the type texts each member
holds or mentions."""

import re
from dataclasses import dataclass
from typing import Iterator

from docgen.clike.body_scan import instantiated_type_texts, iter_method_bodies, scan_body_types
from docgen.clike.modifiers import has_modifier, visibility_from
from docgen.clike.text_scan import PROPERTY_PLACEHOLDER, STATEMENT_END, flatten
from docgen.core.model import Member, MemberKind, Visibility, bare_type_name
from docgen.oo.facts import FieldUsage
from docgen.oo.vocabulary import TypeVocabulary

MODIFIERS_PATTERN = (
    r"(?P<modifiers>"
    r"(?:(?:public|private|protected|internal|abstract|sealed|static|"
    r"readonly|const|new|virtual|override|extern|async|volatile|unsafe|"
    r"event|partial|required)\s+)+"
    r")"
)
NESTED_TYPE = re.compile(r"\b(?:class|interface|enum|struct)\b")
PROPERTY_INNER = re.compile(r"\b(?:get|set|init)\b")
ATTRIBUTES = re.compile(r"^(?:\s*\[[^\]]*\]\s*)+")
PROP_RE = re.compile(MODIFIERS_PATTERN + r"(?P<type>[\w<>?,\[\]\.]+)\s+" + r"(?P<name>\w+)\s*\{")
METHOD_RE = re.compile(
    MODIFIERS_PATTERN
    + r"(?P<return_type>[\w<>?,\[\]\.]+)\s+"
    + r"(?P<name>\w+)\s*"
    + r"(?:<[^>]+>)?\s*"
    + r"\((?P<params>[^)]*)\)",
)
FIELD_RE = re.compile(MODIFIERS_PATTERN + r"(?P<type>[\w<>?,\[\]\.]+)\s+" + r"(?P<name>\w+)")
_INTERFACE_METHOD = re.compile(
    r"(?P<return_type>[\w<>?,\[\]\.]+)\s+(?P<name>\w+)\s*(?:<[^>]+>)?\s*\((?P<params>[^)]*)\)"
)
_INTERFACE_PROPERTY = re.compile(r"(?P<type>[\w<>?,\[\]\.]+)\s+(?P<name>\w+)\s*\{")
_INTERFACE_DECLARATION_NOISE = [re.compile(r"\s*\{\}$"), re.compile(r"\s*\{ get/set \}$"), re.compile(r"^public\s+")]
_PARAMETER_MODIFIER = re.compile(r"^(?:out|ref|in|params)\s+")
_ENUM_ATTRIBUTE = re.compile(r"\[[^\]]*\]")
_ENUM_VALUE_ASSIGNMENT = re.compile(r"=\s*[^\n,]+")
_ENUM_SEPARATORS = re.compile(r"[,\n]")
_IDENTIFIER = re.compile(r"^\w+$")
_VISIBILITY_RULES = [
    ("private protected", Visibility.PRIVATE),
    ("protected internal", Visibility.PROTECTED),
    ("private", Visibility.PRIVATE),
    ("protected", Visibility.PROTECTED),
    ("public", Visibility.PUBLIC),
    ("internal", Visibility.PACKAGE),
]
_NO_RETURN_TYPES = ("void", "async void")
_SERIALIZED_ATTRIBUTE = "[SerializeField]"
_PROPERTY_MARK = PROPERTY_PLACEHOLDER.strip()
_PUBLIC = "public"
_ABSTRACT = "abstract"
_STATIC_KEYWORDS = ("static", "const")
_CALL_OPEN = "("
_KIND_ORDER = {MemberKind.FIELD: 0, MemberKind.PROPERTY: 1, MemberKind.METHOD: 2}


@dataclass(frozen=True)
class MemberTypes:
    """Types held by fields and properties, and types in method signatures."""
    field_usages: list[FieldUsage]
    signature_types: list[str]


def _param_types(raw: str) -> list[str]:
    types = []
    for param in raw.split(","):
        words = _PARAMETER_MODIFIER.sub("", param.strip()).split()
        if words:
            types.append(words[0])
    return types


def _statements(body: str) -> list[str]:
    return flatten(body, NESTED_TYPE, PROPERTY_INNER)


def _typed_member(kind: MemberKind, match: re.Match[str], type_text: str | None) -> Member:
    modifiers = match.group("modifiers").strip()
    parameters = _param_types(match.group("params")) if kind is MemberKind.METHOD else []
    return Member(
        kind=kind, name=match.group("name"), visibility=visibility_from(modifiers, _VISIBILITY_RULES),
        is_static=has_modifier(modifiers, *_STATIC_KEYWORDS), is_abstract=has_modifier(modifiers, _ABSTRACT),
        type=type_text, params=parameters,
    )


def _parse_member(statement: str, class_name: str, vocabulary: TypeVocabulary) -> Member | None:
    """A property, method or field; None for constructors and anything else."""
    declaration = ATTRIBUTES.sub("", statement).strip()
    if _PROPERTY_MARK in declaration and (property_match := PROP_RE.match(declaration)):
        return _typed_member(MemberKind.PROPERTY, property_match, vocabulary.uml_type(property_match.group("type")))
    if _CALL_OPEN in declaration and (method := METHOD_RE.match(declaration)):
        if method.group("name") == class_name:
            return None
        return_type = method.group("return_type")
        return _typed_member(MemberKind.METHOD, method, None if return_type in _NO_RETURN_TYPES else return_type)
    if declaration.endswith(STATEMENT_END) and (field := FIELD_RE.match(declaration)):
        return _typed_member(MemberKind.FIELD, field, vocabulary.uml_type(field.group("type")))
    return None


def class_members(body: str, name: str, vocabulary: TypeVocabulary) -> list[Member]:
    """Fields, then properties, then methods, each in source order."""
    class_name = bare_type_name(name)
    members = [
        member for statement in _statements(body)
        if (member := _parse_member(statement, class_name, vocabulary))
    ]
    return sorted(members, key=lambda member: _KIND_ORDER[member.kind])


def _interface_member(statement: str) -> Member | None:
    """Interface members are shown as declared: always public, types raw,
    every method with its return type (void included)."""
    declaration = ATTRIBUTES.sub("", statement).strip()
    for noise in _INTERFACE_DECLARATION_NOISE:
        declaration = noise.sub("", declaration)
    if method := _INTERFACE_METHOD.match(declaration):
        return Member(kind=MemberKind.METHOD, name=method.group("name"), visibility=Visibility.PUBLIC,
                      is_static=False, is_abstract=False, type=method.group("return_type"),
                      params=_param_types(method.group("params")))
    if property_match := _INTERFACE_PROPERTY.match(declaration):
        return Member(kind=MemberKind.PROPERTY, name=property_match.group("name"), visibility=Visibility.PUBLIC,
                      is_static=False, is_abstract=False, type=property_match.group("type"), params=[])
    return None


def interface_members(body: str) -> list[Member]:
    return [member for statement in _statements(body) if (member := _interface_member(statement))]


def enum_values(body: str) -> list[str]:
    """Constant names only: attributes and explicit values go first."""
    cleaned = _ENUM_VALUE_ASSIGNMENT.sub("", _ENUM_ATTRIBUTE.sub("", body))
    values = [value.strip() for value in _ENUM_SEPARATORS.split(cleaned)]
    return [value for value in values if value and _IDENTIFIER.match(value)]


def _field_usage(raw_statement: str, match: re.Match[str]) -> FieldUsage:
    """raw_statement still holds its attributes."""
    return FieldUsage(
        type_text=match.group("type"),
        is_public=has_modifier(match.group("modifiers"), _PUBLIC),
        is_serialized=_SERIALIZED_ATTRIBUTE in raw_statement,
    )


def _add_member_types(raw_statement: str, class_name: str, types: MemberTypes) -> None:
    declaration = ATTRIBUTES.sub("", raw_statement).strip()
    if _PROPERTY_MARK in declaration:
        if property_match := PROP_RE.match(declaration):
            types.field_usages.append(_field_usage(raw_statement, property_match))
    elif _CALL_OPEN in declaration:
        method = METHOD_RE.match(declaration)
        if method and method.group("name") != class_name:
            types.signature_types.append(method.group("return_type"))
            types.signature_types.extend(_param_types(method.group("params")))
    elif declaration.endswith(STATEMENT_END) and (field := FIELD_RE.match(declaration)):
        types.field_usages.append(_field_usage(raw_statement, field))


def member_types(body: str, name: str) -> MemberTypes:
    """Constructors are not signatures: their parameters aren't usages."""
    class_name = bare_type_name(name)
    types = MemberTypes(field_usages=[], signature_types=[])
    for statement in _statements(body):
        _add_member_types(statement, class_name, types)
    return types


def _method_bodies(body: str) -> Iterator[str]:
    return iter_method_bodies(body, NESTED_TYPE, PROPERTY_INNER)


def body_types(body: str) -> list[str]:
    return [text for method_body in _method_bodies(body) for text in scan_body_types(method_body)]


def newed_types(body: str) -> list[str]:
    return instantiated_type_texts(_method_bodies(body), _statements(body))
