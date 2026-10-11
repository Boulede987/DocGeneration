from docgen.clike.text_scan import strip_c_comments
from docgen.core.model import ParsedFile, ResolutionHints, SourceText, TypeDecl, TypeKind
from docgen.oo.facts import FieldUsage, TypeFacts
from docgen.oo.language import DeclarationWithFacts, ObjectOrientedFacts, ObjectOrientedLanguage, object_oriented_file
from docgen.oo.stereotypes import RECORD_STEREOTYPE, class_stereotype, is_abstract

from . import members
from .declarations import TypeHeader, find_type_headers, parse_imports, parse_package, strip_strings
from .vocabulary import JAVA_VOCABULARY, SKINPARAM_LINES

RECORD = "record"
_KINDS = {
    "class": TypeKind.CLASS,
    "interface": TypeKind.INTERFACE,
    "enum": TypeKind.ENUM,
    RECORD: TypeKind.CLASS,
}


class JavaLanguage(ObjectOrientedLanguage):
    name = "java"
    source_suffix = ".java"
    views_dir = "Packages"
    skinparam_lines = SKINPARAM_LINES
    vocabulary = JAVA_VOCABULARY

    def parse_file(self, source: SourceText) -> ParsedFile[ObjectOrientedFacts]:
        text = strip_strings(strip_c_comments(source.text))
        return object_oriented_file(
            stem=source.stem,
            package=parse_package(text),
            hints=ResolutionHints(type_imports=parse_imports(text)),
            types=[self._parse_type(header) for header in find_type_headers(text)],
        )

    def _parse_type(self, header: TypeHeader) -> DeclarationWithFacts:
        modifiers = frozenset(header.modifiers.split())
        kind = _KINDS[header.kind]
        declaration = TypeDecl(
            name=header.name,
            kind=kind,
            stereotype=class_stereotype(modifiers, RECORD_STEREOTYPE if header.kind == RECORD else None),
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
        """Record components are public fields: listed before the body's
        members, and held types like any field."""
        declaration.members = (
            members.component_members(header.record_params, self.vocabulary)
            + members.class_members(header.body, header.name, self.vocabulary)
        )
        member_types = members.member_types(header.body, header.name)
        facts.field_usages = member_types.field_usages + [
            FieldUsage(type_text=type_text, is_public=True, is_serialized=False)
            for _name, type_text in members.record_components(header.record_params)
        ]
        facts.signature_types = member_types.signature_types
        facts.body_types = members.body_types(header.body)
        facts.newed_types = members.newed_types(header.body)
