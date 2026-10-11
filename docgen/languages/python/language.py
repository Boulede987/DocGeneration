import ast
from typing import Mapping

from docgen.core.model import ParsedFile, SourceText
from docgen.core.project import Project
from docgen.core.relations import Relation
from docgen.oo.language import ObjectOrientedFacts, ObjectOrientedLanguage, object_oriented_file

from .declarations import (
    ABSTRACT_BASE, ENUM_BASES, GENERIC_BASE, OBJECT_BASE, PROTOCOL_BASE, ModuleIdentity, class_declarations,
    module_declaration,
)
from .module_dependencies import module_boxes, module_dependencies
from .modules import PACKAGE_MODULE_STEM, import_hints, imported_names, module_path_of, package_of
from .vocabulary import PYTHON_VOCABULARY, SKINPARAM_LINES

MODULE_BOX_SUFFIX = "_module"
# Bases that only set a class's kind or typing, never drawn as inheritance.
HIDDEN_BASES = frozenset({OBJECT_BASE, ABSTRACT_BASE, GENERIC_BASE, PROTOCOL_BASE}) | ENUM_BASES


class PythonLanguage(ObjectOrientedLanguage):
    """Parsed with the standard library's ast: unparsable text raises (a
    SyntaxError), and only that file fails."""
    name = "python"
    source_suffix = ".py"
    views_dir = "Packages"
    skinparam_lines = SKINPARAM_LINES
    vocabulary = PYTHON_VOCABULARY
    hidden_bases = HIDDEN_BASES

    def parse_file(self, source: SourceText) -> ParsedFile[ObjectOrientedFacts]:
        tree = ast.parse(source.text, filename=str(source.relative_path))
        package = package_of(source.relative_path)
        imported = imported_names(tree, package)
        types = class_declarations(tree, self.vocabulary, imported)
        identity = ModuleIdentity(
            box_name=_module_name(source, {declaration.name for declaration, _facts in types}),
            module_path=module_path_of(source.relative_path),
        )
        module = module_declaration(tree, identity, self.vocabulary, imported)
        if module is not None:
            types.append(module)
        return object_oriented_file(
            stem=source.stem, package=package, hints=import_hints(tree, package), types=types,
        )

    def link(self, project: Project[ObjectOrientedFacts]) -> Mapping[ParsedFile[ObjectOrientedFacts], list[Relation]]:
        """Object-oriented relations, plus dependencies on the module boxes
        whose functions and constants each declaration uses."""
        relations = super().link(project)
        boxes = module_boxes(project)
        return {
            parsed: [*relations.get(parsed, []), *module_dependencies(parsed, boxes)]
            for parsed in project.files
        }


def _module_name(source: SourceText, class_names: set[str]) -> str:
    """The name Python imports it by: a package's own module (__init__.py)
    is its folder's name; a root-level __init__.py has no folder and keeps
    its file name. Suffixed when a class of the module has the same name,
    so the two never merge into one PlantUML entity."""
    folders = source.relative_path.parent.parts
    name = folders[-1] if source.stem == PACKAGE_MODULE_STEM and folders else source.stem
    return name + MODULE_BOX_SUFFIX if name in class_names else name
