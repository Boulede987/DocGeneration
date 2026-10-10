"""Java type bodies -> members, enum constants, record components, and the
type texts each member holds or mentions."""

import re
from dataclasses import dataclass

from docgen.clike.body_scan import instantiated_type_texts, iter_method_bodies, scan_body_types
from docgen.clike.modifiers import has_modifier, visibility_from
from docgen.clike.text_scan import STATEMENT_END, flatten, split_by_comma, split_top_level
from docgen.core.model import FieldUsage, Member, MemberKind, Visibility, bare_type_name
from docgen.core.vocabulary import TypeVocabulary

MODIFIERS_PATTERN = (
    r"(?P<modifiers>"
    r"(?:(?:public|private|protected|static|final|abstract|synchronized|"
    r"native|transient|volatile|strictfp|default)\s+)+"
    r")"
)
NESTED_TYPE = re.compile(r"\b(?:class|interface|enum|record)\b")
ANNOTATIONS = re.compile(r"^(?:\s*@\w+(?:\([^)]*\))?\s*)+")
METHOD_RE = re.compile(
    MODIFIERS_PATTERN
    + r"(?:<[^>]+>\s+)?"                           # method-level type parameters are not the return type
    + r"(?P<return_type>[\w<>\[\],\.\? ]+(?:\[\])*)\s+"
    + r"(?P<name>\w+)\s*"
    + r"\((?P<params>[^)]*)\)",
)
FIELD_RE = re.compile(
    MODIFIERS_PATTERN
    + r"(?P<type>[\w<>\[\],\.\? ]+(?:\[\])*)\s+"
    + r"(?P<name>\w+)",
)
_INTERFACE_METHOD = re.compile(
    r"(?P<return_type>[\w<>\[\],\.\? ]+)\s+(?P<name>\w+)\s*(?:<[^>]+>)?\s*\((?P<params>[^)]*)\)"
)
_INTERFACE_CONSTANT = re.compile(r"(?P<type>[\w<>\[\],\.\? ]+)\s+(?P<name>\w+)")
_INTERFACE_MODIFIERS = re.compile(r"^(?:(?:public|abstract|default|static|final)\s+)+")
_DEFAULT_METHOD_BODY = re.compile(r"\s*\{[^{}]*\}$")
_FINAL_PARAMETER = re.compile(r"^(?:final)\s+")
_ENUM_ANNOTATION = re.compile(r"@\w+(?:\([^)]*\))?")
_ENUM_CONSTRUCTOR_ARGUMENTS = re.compile(r"\([^()]*\)")
_ENUM_CONSTANT_BODY = re.compile(r"\{[^{}]*\}")
_IDENTIFIER = re.compile(r"^\w+$")
_VISIBILITY_RULES = [
    ("private", Visibility.PRIVATE),
    ("protected", Visibility.PROTECTED),
    ("public", Visibility.PUBLIC),
]
_VOID = "void"
_VARARGS = "..."
_ARRAY = "[]"
_PUBLIC = "public"
_STATIC = "static"
_ABSTRACT = "abstract"
_CALL_OPEN = "("


@dataclass(frozen=True)
class MemberTypes:
    """Types held by fields, and types in method signatures."""
    field_usages: list[FieldUsage]
    signature_types: list[str]


def _param_types(raw: str) -> list[str]:
    types = []
    for param in raw.split(","):
        words = _FINAL_PARAMETER.sub("", param.strip()).replace(_VARARGS, _ARRAY).split()
        if words:
            types.append(words[0])
    return types


def _statements(body: str) -> list[str]:
    """Member statements, annotations removed."""
    return [ANNOTATIONS.sub("", statement).strip() for statement in flatten(body, NESTED_TYPE)]


def _typed_member(kind: MemberKind, modifiers: str, name: str, type_text: str | None, params: list[str]) -> Member:
    return Member(
        kind=kind, name=name, visibility=visibility_from(modifiers, _VISIBILITY_RULES),
        is_static=has_modifier(modifiers, _STATIC), is_abstract=has_modifier(modifiers, _ABSTRACT),
        type=type_text, params=params,
    )


def _method(match: re.Match[str]) -> Member:
    return_type = match.group("return_type")
    return _typed_member(MemberKind.METHOD, match.group("modifiers").strip(), match.group("name"),
                         None if return_type == _VOID else return_type, _param_types(match.group("params")))


def _parse_member(statement: str, class_name: str, vocabulary: TypeVocabulary) -> Member | None:
    """A field or a method; None for constructors and anything else."""
    method = METHOD_RE.match(statement) if _CALL_OPEN in statement else None
    if method:
        return _method(method) if method.group("name") != class_name else None
    field = FIELD_RE.match(statement) if statement.endswith(STATEMENT_END) else None
    if field:
        return _typed_member(MemberKind.FIELD, field.group("modifiers").strip(), field.group("name"),
                             vocabulary.uml_type(field.group("type")), [])
    return None


def class_members(body: str, name: str, vocabulary: TypeVocabulary) -> list[Member]:
    """Fields first, then methods, each in source order."""
    class_name = bare_type_name(name)
    members = [
        member for statement in _statements(body)
        if (member := _parse_member(statement, class_name, vocabulary))
    ]
    return sorted(members, key=lambda member: member.kind is MemberKind.METHOD)


def record_components(raw: str | None) -> list[tuple[str, str]]:
    """'(int x, List<Y> ys)' -> [('x', 'int'), ('ys', 'List<Y>')]."""
    if not raw:
        return []
    inner = raw.strip()
    if inner.startswith("(") and inner.endswith(")"):
        inner = inner[1:-1]
    components = []
    for part in split_by_comma(inner):
        declaration = ANNOTATIONS.sub("", part).strip().replace(_VARARGS, _ARRAY)
        type_and_name = declaration.rsplit(None, 1)
        if len(type_and_name) == 2:
            type_text, component_name = type_and_name
            components.append((component_name, type_text))
    return components


def component_members(raw: str | None, vocabulary: TypeVocabulary) -> list[Member]:
    return [
        Member(kind=MemberKind.FIELD, name=name, visibility=Visibility.PUBLIC, is_static=False,
               is_abstract=False, type=vocabulary.uml_type(type_text), params=[])
        for name, type_text in record_components(raw)
    ]


def _interface_member(statement: str) -> Member | None:
    """Interface members are shown as declared: always public, types raw,
    every method with its return type (void included)."""
    declaration = _INTERFACE_MODIFIERS.sub("", _DEFAULT_METHOD_BODY.sub("", statement))
    if method := _INTERFACE_METHOD.match(declaration):
        return Member(kind=MemberKind.METHOD, name=method.group("name"), visibility=Visibility.PUBLIC,
                      is_static=False, is_abstract=False, type=method.group("return_type"),
                      params=_param_types(method.group("params")))
    constant = _INTERFACE_CONSTANT.match(declaration) if declaration.endswith(STATEMENT_END) else None
    if constant:
        return Member(kind=MemberKind.FIELD, name=constant.group("name"), visibility=Visibility.PUBLIC,
                      is_static=True, is_abstract=False, type=constant.group("type"), params=[])
    return None


def interface_members(body: str) -> list[Member]:
    return [member for statement in _statements(body) if (member := _interface_member(statement))]


def enum_values(body: str) -> list[str]:
    """Constant names only: annotations, constructor arguments and
    constant-specific bodies may contain commas, so they go first."""
    constants, _members = split_top_level(body, STATEMENT_END)
    for pattern in (_ENUM_ANNOTATION, _ENUM_CONSTRUCTOR_ARGUMENTS, _ENUM_CONSTANT_BODY):
        constants = pattern.sub("", constants)
    values = [value.strip() for value in constants.split(",")]
    return [value for value in values if value and _IDENTIFIER.match(value)]


def _add_member_types(statement: str, class_name: str, types: MemberTypes) -> None:
    if _CALL_OPEN in statement:
        method = METHOD_RE.match(statement)
        if method and method.group("name") != class_name:
            types.signature_types.append(method.group("return_type"))
            types.signature_types.extend(_param_types(method.group("params")))
        return
    field = FIELD_RE.match(statement) if statement.endswith(STATEMENT_END) else None
    if field:
        is_public = has_modifier(field.group("modifiers"), _PUBLIC)
        types.field_usages.append(FieldUsage(type_text=field.group("type"), is_public=is_public, is_serialized=False))


def member_types(body: str, name: str) -> MemberTypes:
    """Constructors are not signatures: their parameters aren't usages."""
    class_name = bare_type_name(name)
    types = MemberTypes(field_usages=[], signature_types=[])
    for statement in _statements(body):
        _add_member_types(statement, class_name, types)
    return types


def body_types(body: str) -> list[str]:
    return [text for method_body in iter_method_bodies(body, NESTED_TYPE) for text in scan_body_types(method_body)]


def newed_types(body: str) -> list[str]:
    return instantiated_type_texts(iter_method_bodies(body, NESTED_TYPE), flatten(body, NESTED_TYPE))
