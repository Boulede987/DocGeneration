import ast

from docgen.core.language import Language
from docgen.core.model import ParsedFile, SourceText, TypeDecl

from .declarations import (
    ABSTRACT_BASE, DATACLASS_MODIFIER, ENUM_BASES, GENERIC_BASE, OBJECT_BASE, PROTOCOL_BASE, class_declarations,
    module_declaration,
)
from .modules import import_hints, package_of
from .vocabulary import DATACLASS_STYLE, PYTHON_VOCABULARY, SKINPARAM_LINES

DATACLASS_STEREOTYPE = f"<<{DATACLASS_STYLE.stereotype}>>"
PACKAGE_MODULE_STEM = "__init__"
MODULE_BOX_SUFFIX = "_module"
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
        declarations = class_declarations(tree, self.vocabulary)
        module_name = _module_name(source, {declaration.name for declaration in declarations})
        module = module_declaration(tree, module_name, self.vocabulary)
        return ParsedFile(
            stem=source.stem,
            package=package,
            declarations=declarations + ([] if module is None else [module]),
            hints=import_hints(tree, package),
        )

    def class_stereotype(self, declaration: TypeDecl) -> str | None:
        if DATACLASS_MODIFIER in declaration.modifiers:
            return DATACLASS_STEREOTYPE
        return super().class_stereotype(declaration)


def _module_name(source: SourceText, class_names: set[str]) -> str:
    """The name Python imports it by: a package's own module (__init__.py)
    is its folder's name; a root-level __init__.py has no folder and keeps
    its file name. Suffixed when a class of the module has the same name,
    so the two never merge into one PlantUML entity."""
    folders = source.relative_path.parent.parts
    name = folders[-1] if source.stem == PACKAGE_MODULE_STEM and folders else source.stem
    return name + MODULE_BOX_SUFFIX if name in class_names else name
