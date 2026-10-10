import ast

from docgen.core.language import Language
from docgen.core.model import ParsedFile, SourceText, TypeDecl

from .declarations import (
    ABSTRACT_BASE, DATACLASS_MODIFIER, ENUM_BASES, GENERIC_BASE, OBJECT_BASE, PROTOCOL_BASE, class_declarations,
)
from .modules import import_hints, package_of
from .vocabulary import DATACLASS_STYLE, PYTHON_VOCABULARY, SKINPARAM_LINES

DATACLASS_STEREOTYPE = f"<<{DATACLASS_STYLE.stereotype}>>"
# Bases that only set a class's kind or typing, never drawn as inheritance.
HIDDEN_BASES = frozenset({OBJECT_BASE, ABSTRACT_BASE, GENERIC_BASE, PROTOCOL_BASE}) | ENUM_BASES


class PythonLanguage(Language):
    """Parsed with the standard library's ast: unparsable text raises (a
    SyntaxError), and only that file fails."""
    name = "python"
    source_suffix = ".py"
    views_dir = "Packages"
    skinparam_lines = SKINPARAM_LINES
    vocabulary = PYTHON_VOCABULARY
    hidden_bases = HIDDEN_BASES

    def parse_file(self, source: SourceText) -> ParsedFile:
        tree = ast.parse(source.text, filename=str(source.relative_path))
        package = package_of(source.relative_path)
        return ParsedFile(
            stem=source.stem,
            package=package,
            declarations=class_declarations(tree, self.vocabulary),
            hints=import_hints(tree, package),
        )

    def class_stereotype(self, declaration: TypeDecl) -> str | None:
        if DATACLASS_MODIFIER in declaration.modifiers:
            return DATACLASS_STEREOTYPE
        return super().class_stereotype(declaration)
