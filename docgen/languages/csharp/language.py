from docgen.clike.text_scan import strip_c_comments
from docgen.core import style
from docgen.core.model import ParsedFile, ResolutionHints, SourceText, TypeDecl, TypeKind
from docgen.oo.facts import TypeFacts
from docgen.oo.language import DeclarationWithFacts, ObjectOrientedFacts, ObjectOrientedLanguage, object_oriented_file
from docgen.oo.stereotypes import STRUCT_STEREOTYPE, class_stereotype, is_abstract

from . import members
from .declarations import TypeHeader, find_type_headers, parse_namespace, parse_usings, strip_strings
from .vocabulary import CSHARP_VOCABULARY, STRUCT_STYLE

STRUCT = "struct"
_KINDS = {
    "class": TypeKind.CLASS,
    "interface": TypeKind.INTERFACE,
    "enum": TypeKind.ENUM,
    STRUCT: TypeKind.CLASS,
}
_NAMESPACE_SEPARATOR = "."


class CSharpLanguage(ObjectOrientedLanguage):
    """Only a file's first namespace is read: every type in the file is
    placed in it."""
    name = "csharp"
    source_suffix = ".cs"
    views_dir = "Namespaces"
    skinparam_lines = style.skinparam_lines([STRUCT_STYLE])
    vocabulary = CSHARP_VOCABULARY

    def parse_file(self, source: SourceText) -> ParsedFile[ObjectOrientedFacts]:
        text = strip_strings(strip_c_comments(source.text))
        return object_oriented_file(
            stem=source.stem,
            package=parse_namespace(text),
            hints=ResolutionHints(namespace_imports=parse_usings(text)),
            types=[self._parse_type(header) for header in find_type_headers(text)],
        )

    def enclosing_packages(self, package: str | None) -> list[str | None]:
        """A.B.C sees A.B.C, A.B, A and the global namespace (None) without
        a using directive."""
        parts = package.split(_NAMESPACE_SEPARATOR) if package else []
        enclosing: list[str | None] = [
            _NAMESPACE_SEPARATOR.join(parts[:depth]) for depth in range(len(parts), 0, -1)
        ]
        return enclosing + [None]

    def stereotype(self, header: TypeHeader, modifiers: frozenset[str]) -> str | None:
        """Overridable: Unity marks ScriptableObject subclasses."""
        return class_stereotype(modifiers, STRUCT_STEREOTYPE if header.kind == STRUCT else None)

    def _parse_type(self, header: TypeHeader) -> DeclarationWithFacts:
        modifiers = frozenset(header.modifiers.split())
        kind = _KINDS[header.kind]
        declaration = TypeDecl(
            name=header.name,
            kind=kind,
            stereotype=self.stereotype(header, modifiers),
            is_abstract=is_abstract(modifiers),
        )
        facts = TypeFacts(name=header.name, base_class=header.base_class, interfaces=header.interfaces)
        if kind is TypeKind.ENUM:
            declaration.enum_values = members.enum_values(header.body)
        elif kind is TypeKind.INTERFACE:
            declaration.members = members.interface_members(header.body)
        else:
            self._fill_class_like(declaration, facts, header)
        return declaration, facts

    def _fill_class_like(self, declaration: TypeDecl, facts: TypeFacts, header: TypeHeader) -> None:
        declaration.members = members.class_members(header.body, header.name, self.vocabulary)
        member_types = members.member_types(header.body, header.name)
        facts.field_usages = member_types.field_usages
        facts.signature_types = member_types.signature_types
        facts.body_types = members.body_types(header.body)
        facts.newed_types = members.newed_types(header.body)
