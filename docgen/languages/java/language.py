from docgen.clike.text_scan import strip_c_comments
from docgen.core.language import Language
from docgen.core.model import FieldUsage, ParsedFile, ResolutionHints, TypeDecl, TypeKind

from . import members
from .declarations import TypeHeader, find_type_headers, parse_imports, parse_package, strip_strings
from .vocabulary import JAVA_VOCABULARY, SKINPARAM_LINES

_KINDS = {
    "class": TypeKind.CLASS,
    "interface": TypeKind.INTERFACE,
    "enum": TypeKind.ENUM,
    "record": TypeKind.RECORD,
}


class JavaLanguage(Language):
    name = "java"
    source_suffix = ".java"
    views_dir = "Packages"
    skinparam_lines = SKINPARAM_LINES
    vocabulary = JAVA_VOCABULARY

    def parse_file(self, stem: str, source: str) -> ParsedFile:
        text = strip_strings(strip_c_comments(source))
        return ParsedFile(
            stem=stem,
            package=parse_package(text),
            declarations=[self._declaration(header) for header in find_type_headers(text)],
            hints=ResolutionHints(type_imports=parse_imports(text)),
        )

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
        """Record components are public fields: listed before the body's
        members, and held types like any field."""
        declaration.members = (
            members.component_members(header.record_params, self.vocabulary)
            + members.class_members(header.body, header.name, self.vocabulary)
        )
        member_types = members.member_types(header.body, header.name)
        declaration.field_usages = member_types.field_usages + [
            FieldUsage(type_text=type_text, is_public=True, is_serialized=False)
            for _name, type_text in members.record_components(header.record_params)
        ]
        declaration.signature_types = member_types.signature_types
        declaration.body_types = members.body_types(header.body)
        declaration.newed_types = members.newed_types(header.body)
