"""A deliberately tiny language, defined entirely outside docgen, to prove a
new language plugs into the shared pipeline through the public interface
alone. Syntax, one declaration per line:

    package zoo
    class Dog extends Animal
      field owner: Person
"""

from docgen.core.language import Language
from docgen.core.model import (
    FieldUsage, Member, MemberKind, ParsedFile, ResolutionHints, TypeDecl, TypeKind, Visibility,
)
from docgen.core.vocabulary import TypeVocabulary

EXTENDS_KEYWORD = "extends"


class ToySyntaxError(ValueError):
    pass


class ToyLanguage(Language):
    name = "toy"
    source_suffix = ".toy"
    views_dir = "Modules"
    skinparam_lines = ["skinparam shadowing false"]
    vocabulary = TypeVocabulary(primitives=frozenset({"int", "str"}), collection_wrappers=frozenset())

    def parse_file(self, stem: str, source: str) -> ParsedFile:
        parsed = ParsedFile(stem=stem, package=None, declarations=[], hints=ResolutionHints())
        for line_number, line in enumerate(source.splitlines(), start=1):
            words = line.replace(":", " ").split()
            if words:
                _apply_line(parsed, words, line_number)
        return parsed


def _apply_line(parsed: ParsedFile, words: list[str], line_number: int) -> None:
    keyword, arguments = words[0], words[1:]
    if keyword == "package" and len(arguments) == 1:
        parsed.package = arguments[0]
    elif keyword == "class" and len(arguments) in (1, 3):
        parsed.declarations.append(_toy_class(arguments, line_number))
    elif keyword == "field" and len(arguments) == 2 and parsed.declarations:
        _add_field(parsed.declarations[-1], field_name=arguments[0], type_text=arguments[1])
    else:
        raise ToySyntaxError(f"line {line_number}: cannot parse {' '.join(words)!r}")


def _toy_class(arguments: list[str], line_number: int) -> TypeDecl:
    """'Dog' or 'Dog extends Animal'."""
    name, *inheritance = arguments
    if inheritance and inheritance[0] != EXTENDS_KEYWORD:
        raise ToySyntaxError(f"line {line_number}: expected '{EXTENDS_KEYWORD}'")
    return TypeDecl(name=name, kind=TypeKind.CLASS, base_class=inheritance[1] if inheritance else None)


def _add_field(declaration: TypeDecl, field_name: str, type_text: str) -> None:
    declaration.members.append(Member(
        kind=MemberKind.FIELD, name=field_name, visibility=Visibility.PRIVATE,
        is_static=False, is_abstract=False, type=type_text, params=[],
    ))
    declaration.field_usages.append(FieldUsage(type_text=type_text, is_public=False, is_serialized=False))
