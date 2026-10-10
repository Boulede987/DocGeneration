from docgen.clike.text_scan import strip_c_comments
from docgen.core import style
from docgen.core.language import Language
from docgen.core.model import ParsedFile, ResolutionHints, TypeDecl, TypeKind

from . import members
from .declarations import TypeHeader, find_type_headers, parse_namespace, parse_usings, strip_strings
from .vocabulary import CSHARP_VOCABULARY, STRUCT_STYLE

_KINDS = {
    "class": TypeKind.CLASS,
    "interface": TypeKind.INTERFACE,
    "enum": TypeKind.ENUM,
    "struct": TypeKind.STRUCT,
}
_NAMESPACE_SEPARATOR = "."


class CSharpLanguage(Language):
    """Only a file's first namespace is read: every type in the file is
    placed in it."""
    name = "csharp"
    source_suffix = ".cs"
    views_dir = "Namespaces"
    skinparam_lines = style.skinparam_lines([STRUCT_STYLE])
    vocabulary = CSHARP_VOCABULARY

    def parse_file(self, stem: str, source: str) -> ParsedFile:
        text = strip_strings(strip_c_comments(source))
        return ParsedFile(
            stem=stem,
            package=parse_namespace(text),
            declarations=[self._declaration(header) for header in find_type_headers(text)],
            hints=ResolutionHints(namespace_imports=parse_usings(text)),
        )

    def enclosing_packages(self, package: str | None) -> list[str | None]:
        """A.B.C sees A.B.C, A.B, A and the global namespace (None) without
        a using directive."""
        parts = package.split(_NAMESPACE_SEPARATOR) if package else []
        enclosing: list[str | None] = [
            _NAMESPACE_SEPARATOR.join(parts[:depth]) for depth in range(len(parts), 0, -1)
        ]
        return enclosing + [None]

    def _declaration(self, header: TypeHeader) -> TypeDecl:
        declaration = TypeDecl(
            name=header.name,
            kind=_KINDS[header.kind],
            modifiers=frozenset(header.modifiers.split()),
            base_class=header.base_class,
            interfaces=header.interfaces,
        )
        if declaration.kind is TypeKind.ENUM:
            declaration.enum_values = members.enum_values(header.body)
        elif declaration.kind is TypeKind.INTERFACE:
            declaration.members = members.interface_members(header.body)
        else:
            self._fill_class_like(declaration, header)
        return declaration

    def _fill_class_like(self, declaration: TypeDecl, header: TypeHeader) -> None:
        declaration.members = members.class_members(header.body, header.name, self.vocabulary)
        member_types = members.member_types(header.body, header.name)
        declaration.field_usages = member_types.field_usages
        declaration.signature_types = member_types.signature_types
        declaration.body_types = members.body_types(header.body)
        declaration.newed_types = members.newed_types(header.body)
