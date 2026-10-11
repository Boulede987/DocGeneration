"""How a language's type texts are read: which names are built-in (never
project types), which wrappers mean "a collection of"."""

import re
from dataclasses import dataclass

from docgen.core.model import TYPE_PARAMETERS_START

TYPE_PARAMETERS_END = ">"
_TYPE_TEXT_SEPARATORS = re.compile(r"[<>,\[\]\s\.\*\(\)]+")
_TYPE_NAME = re.compile(r"^_*[A-Z]\w*$")  # leading underscores: private classes
_ARRAY_SUFFIX = "[]"
_UML_MANY_SUFFIX = "[*]"
_NULLABLE_MARK = "?"


@dataclass(frozen=True)
class TypeVocabulary:
    """type_argument_brackets: how the language writes type arguments,
    e.g. ("<", ">") for List<Foo>, ("[", "]") for list[Foo]."""
    primitives: frozenset[str]
    collection_wrappers: frozenset[str]
    type_argument_brackets: tuple[str, str] = (TYPE_PARAMETERS_START, TYPE_PARAMETERS_END)

    def __post_init__(self) -> None:
        opening, closing = self.type_argument_brackets
        if not opening or not closing or opening == closing:
            raise ValueError(f"type_argument_brackets must be two distinct, non-empty strings, "
                             f"got {self.type_argument_brackets!r}")

    def _wrapper(self, type_text: str) -> str:
        return type_text.split(self.type_argument_brackets[0])[0]

    def is_collection(self, type_text: str) -> bool:
        text = type_text.rstrip(_NULLABLE_MARK)
        if text.endswith(_ARRAY_SUFFIX):
            return True
        return self._wrapper(text) in self.collection_wrappers

    def uml_type(self, type_text: str) -> str:
        """Collections become multiplicity notation: List<Foo> -> Foo[*]."""
        text = type_text.strip()
        if text.endswith(_ARRAY_SUFFIX):
            return text[:-len(_ARRAY_SUFFIX)] + _UML_MANY_SUFFIX
        wrapper = self._wrapper(text)
        if wrapper not in self.collection_wrappers:
            return text
        opening, closing = self.type_argument_brackets
        type_arguments = text[len(wrapper):]
        if type_arguments.startswith(opening) and type_arguments.endswith(closing):
            return type_arguments[len(opening):-len(closing)].strip() + _UML_MANY_SUFFIX
        return text

    def type_names(self, type_text: str) -> set[str]:
        """Capitalized, non-built-in names in a possibly generic/array type."""
        tokens = _TYPE_TEXT_SEPARATORS.split(type_text.rstrip(_NULLABLE_MARK))
        return {
            token for token in tokens
            if token and _TYPE_NAME.match(token) and token not in self.primitives
        }
