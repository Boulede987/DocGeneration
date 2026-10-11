"""Base class for languages whose relations follow object-oriented rules:
inheritance from bases, composition/association from fields, dependencies
from signatures and bodies."""

from typing import Mapping

from docgen.core.language import Language
from docgen.core.model import ParsedFile, ResolutionHints, TypeDecl
from docgen.core.project import Project
from docgen.core.relations import Relation

from .facts import TypeFacts
from .inference import RelationPolicy, relations_of
from .vocabulary import TypeVocabulary

ObjectOrientedFacts = list[TypeFacts]
DeclarationWithFacts = tuple[TypeDecl, TypeFacts]


def object_oriented_file(
    stem: str, package: str | None, hints: ResolutionHints, types: list[DeclarationWithFacts],
) -> ParsedFile[ObjectOrientedFacts]:
    """The one place declarations and their facts are split: facts[i]
    describes declarations[i]."""
    return ParsedFile(
        stem=stem,
        package=package,
        declarations=[declaration for declaration, _facts in types],
        hints=hints,
        facts=[facts for _declaration, facts in types],
    )


class ObjectOrientedLanguage(Language[ObjectOrientedFacts]):
    """A parser stores one TypeFacts per declaration in ParsedFile.facts.
    Class attributes, besides Language's:
    vocabulary      built-in types and collection wrappers
    hidden_bases    base classes never drawn as an inheritance arrow
    """
    vocabulary: TypeVocabulary
    hidden_bases: frozenset[str] = frozenset()

    def relation_policy(self, project: Project[ObjectOrientedFacts]) -> RelationPolicy:
        """Built once per link, after every file is parsed, so a policy may
        depend on the whole project."""
        return RelationPolicy()

    def link(self, project: Project[ObjectOrientedFacts]) -> Mapping[ParsedFile[ObjectOrientedFacts], list[Relation]]:
        policy = self.relation_policy(project)
        known_types = project.index.known_types()
        return {
            parsed: relations_of(parsed.facts or [], known_types, policy, self.vocabulary, self.hidden_bases)
            for parsed in project.files
        }
