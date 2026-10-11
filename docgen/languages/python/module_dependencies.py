"""Dependencies on other modules' free functions and constants, drawn to
their <<module>> box. Needs the whole project: whether an imported name is
a function or constant of a project module is only known once every file
is parsed (flow: docs/Algorithms/module_dependencies.puml)."""

from dataclasses import dataclass

from docgen.core.model import ParsedFile, TypeDecl
from docgen.core.project import Project
from docgen.core.relations import DEPENDS, Relation, RelationLevel
from docgen.oo.language import ObjectOrientedFacts

from .declarations import PythonTypeFacts
from .modules import ModuleUse


@dataclass(frozen=True)
class ModuleBox:
    name: str
    package: str | None
    member_names: frozenset[str]


def _declarations_with_facts(parsed: ParsedFile[ObjectOrientedFacts]) -> list[tuple[TypeDecl, PythonTypeFacts]]:
    """facts[i] describes declarations[i]; the Python parser gives every
    declaration PythonTypeFacts."""
    return [
        (declaration, facts)
        for declaration, facts in zip(parsed.declarations, parsed.facts or [], strict=True)
        if isinstance(facts, PythonTypeFacts)
    ]


def module_boxes(project: Project[ObjectOrientedFacts]) -> dict[str, ModuleBox]:
    """Every module box, by the module path it's imported by."""
    return {
        facts.module_path: ModuleBox(
            declaration.name, parsed.package, frozenset(member.name for member in declaration.members),
        )
        for parsed in project.files
        for declaration, facts in _declarations_with_facts(parsed)
        if facts.module_path is not None
    }


def _used_box(use: ModuleUse, own_module_path: str | None, boxes: dict[str, ModuleBox]) -> ModuleBox | None:
    """The box defining the used name, unless it's the user's own module."""
    box = boxes.get(use.module_path)
    if box is None or use.name not in box.member_names or use.module_path == own_module_path:
        return None
    return box


def module_dependencies(parsed: ParsedFile[ObjectOrientedFacts], boxes: dict[str, ModuleBox]) -> list[Relation]:
    """One weak dependency per (declaration, used box), with the box's
    package given: several modules may share a name (every language has a
    vocabulary.py), and the import already says which one is meant."""
    relations: list[Relation] = []
    for declaration, facts in _declarations_with_facts(parsed):
        used = (_used_box(use, facts.module_path, boxes) for use in facts.module_uses)
        for box in dict.fromkeys(box for box in used if box is not None):
            relations.append(
                Relation(declaration.name, DEPENDS, box.name, RelationLevel.WEAK, target_package=box.package)
            )
    return relations
