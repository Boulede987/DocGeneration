"""A deliberately tiny language, defined entirely outside docgen and without
the object-oriented toolkit (docgen.oo), to prove a language plugs into the
core through its public contract alone: it parses, computes its own
relations, and merges declarations across files. Syntax, one statement per
line:

    package zoo
    class Dog extends Animal
      field owner: Person
    extend Dog              (in any file: the following fields join Dog)
      field collar: Collar
"""

from dataclasses import dataclass, field
from typing import Mapping

from docgen.core.language import Language
from docgen.core.model import Member, MemberKind, ParsedFile, ResolutionHints, SourceText, TypeDecl, TypeKind, Visibility
from docgen.core.project import Project
from docgen.core.relations import ASSOCIATES, INHERITS, Relation, RelationLevel

EXTENDS_KEYWORD = "extends"
TOY_STEREOTYPE = "<<toy>>"


class ToySyntaxError(ValueError):
    pass


@dataclass
class ToyType:
    """What the toy parser knows about one class, beyond the UML box."""
    name: str
    base: str | None
    field_types: list[str] = field(default_factory=list)


@dataclass
class ToyExtension:
    target: str
    fields: list[tuple[str, str]] = field(default_factory=list)


@dataclass
class ToyFacts:
    types: list[ToyType] = field(default_factory=list)
    extensions: list[ToyExtension] = field(default_factory=list)
    receiving_fields: ToyType | ToyExtension | None = None  # the latest class or extend


class ToyLanguage(Language[ToyFacts]):
    """Parsing keeps what relations need in ToyFacts; link() merges the
    'extend' blocks, then derives relations from the merged facts."""
    name = "toy"
    source_suffix = ".toy"
    views_dir = "Modules"
    skinparam_lines = ["skinparam shadowing false"]

    def parse_file(self, source: SourceText) -> ParsedFile[ToyFacts]:
        """One file, alone. No imports in toy: every name is looked up in
        the file's own package (empty hints)."""
        parsed = ParsedFile(stem=source.stem, package=None, declarations=[], hints=ResolutionHints(), facts=ToyFacts())
        for line_number, line in enumerate(source.text.splitlines(), start=1):
            if statement := line.strip():
                _apply_statement(parsed, statement, line_number)
        return parsed

    def link(self, project: Project[ToyFacts]) -> Mapping[ParsedFile[ToyFacts], list[Relation]]:
        """Merges first, so a field added by 'extend' gets its relation."""
        for parsed in project.files:
            for extension in parsed.facts.extensions:
                _merge(project, parsed, extension)
        known = project.index.known_types()
        return {parsed: _relations(parsed.facts, known) for parsed in project.files}


def _apply_statement(parsed: ParsedFile[ToyFacts], statement: str, line_number: int) -> None:
    words = statement.replace(":", " ").split()
    keyword, arguments = words[0], words[1:]
    if keyword == "package" and len(arguments) == 1:
        parsed.package = arguments[0]
    elif keyword == "class" and len(arguments) in (1, 3):
        _add_class(parsed, arguments, line_number)
    elif keyword == "extend" and len(arguments) == 1:
        parsed.facts.extensions.append(ToyExtension(arguments[0]))
        parsed.facts.receiving_fields = parsed.facts.extensions[-1]
    elif keyword == "field" and len(arguments) == 2 and isinstance(parsed.facts.receiving_fields, ToyExtension):
        parsed.facts.receiving_fields.fields.append((arguments[0], arguments[1]))
    elif keyword == "field" and len(arguments) == 2 and parsed.declarations:
        _add_field(parsed.declarations[-1], parsed.facts.types[-1], arguments[0], arguments[1])
    else:
        raise ToySyntaxError(f"line {line_number}: cannot parse {statement!r}")


def _add_class(parsed: ParsedFile[ToyFacts], arguments: list[str], line_number: int) -> None:
    name, *inheritance = arguments
    if inheritance and inheritance[0] != EXTENDS_KEYWORD:
        raise ToySyntaxError(f"line {line_number}: expected '{EXTENDS_KEYWORD}'")
    parsed.declarations.append(TypeDecl(name=name, kind=TypeKind.CLASS, stereotype=TOY_STEREOTYPE))
    parsed.facts.types.append(ToyType(name, inheritance[1] if inheritance else None))
    parsed.facts.receiving_fields = parsed.facts.types[-1]


def _add_field(declaration: TypeDecl, toy_type: ToyType, field_name: str, type_text: str) -> None:
    declaration.members.append(Member(
        kind=MemberKind.FIELD, name=field_name, visibility=Visibility.PRIVATE,
        is_static=False, is_abstract=False, type=type_text, params=[],
    ))
    toy_type.field_types.append(type_text)


def _find_class(project: Project[ToyFacts], name: str) -> tuple[TypeDecl, ToyType] | None:
    """The first class with this name. Every toy declaration is a class, so
    declarations and facts.types are parallel."""
    return next(
        (
            (declaration, toy_type)
            for parsed in project.files
            for declaration, toy_type in zip(parsed.declarations, parsed.facts.types)
            if declaration.name == name
        ),
        None,
    )


def _merge(project: Project[ToyFacts], origin: ParsedFile[ToyFacts], extension: ToyExtension) -> None:
    found = _find_class(project, extension.target)
    if found is None:
        origin.notes.append(f"extend {extension.target}: no such class")
        return
    declaration, toy_type = found
    for field_name, type_text in extension.fields:
        _add_field(declaration, toy_type, field_name, type_text)


def _relations(facts: ToyFacts, known: set[str]) -> list[Relation]:
    """A base is drawn even when unknown (it's declared as one); a field
    type only when it's a project class, so 'str' draws nothing."""
    relations = [
        Relation(toy_type.name, INHERITS, toy_type.base, RelationLevel.INHERITANCE)
        for toy_type in facts.types if toy_type.base
    ]
    relations += [
        Relation(toy_type.name, ASSOCIATES, type_text, RelationLevel.WEAK)
        for toy_type in facts.types for type_text in toy_type.field_types if type_text in known
    ]
    return relations
