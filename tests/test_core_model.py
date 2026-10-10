"""Core building blocks language authors use directly: TypeVocabulary and
inheritance relations."""

import pytest

from docgen.core.model import TypeDecl, TypeKind
from docgen.core.relations import inheritance_relations
from docgen.core.vocabulary import TypeVocabulary

SQUARE_BRACKETS = ("[", "]")


def _python_like_vocabulary() -> TypeVocabulary:
    return TypeVocabulary(
        primitives=frozenset(), collection_wrappers=frozenset({"list"}), type_argument_brackets=SQUARE_BRACKETS,
    )


def test_square_bracket_collection_becomes_multiplicity():
    assert _python_like_vocabulary().uml_type("list[Item]") == "Item[*]"


def test_square_bracket_collection_is_recognized():
    assert _python_like_vocabulary().is_collection("list[Item]")


@pytest.mark.parametrize("brackets", [("", ">"), ("<", ""), ("|", "|")])
def test_vocabulary_rejects_empty_or_identical_brackets(brackets: tuple[str, str]):
    with pytest.raises(ValueError, match="type_argument_brackets"):
        TypeVocabulary(primitives=frozenset(), collection_wrappers=frozenset(), type_argument_brackets=brackets)


def test_a_base_listed_twice_draws_one_arrow():
    declaration = TypeDecl(name="Child", kind=TypeKind.CLASS, base_class="Parent", additional_bases=["Parent", "Mixin"])

    targets = [relation.target for relation in inheritance_relations(declaration, frozenset())]

    assert targets == ["Parent", "Mixin"]
