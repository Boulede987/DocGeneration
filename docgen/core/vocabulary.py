"""How a language's type texts are read: which names are built-in (never
project types), which wrappers mean "a collection of"."""

import re
from dataclasses import dataclass

from .model import TYPE_PARAMETERS_START, bare_type_name

_TYPE_PARAMETERS_END = ">"
_TYPE_TEXT_SEPARATORS = re.compile(r"[<>,\[\]\s\.\*\(\)]+")
_TYPE_NAME = re.compile(r"^[A-Z]\w*$")
_ARRAY_SUFFIX = "[]"
_UML_MANY_SUFFIX = "[*]"
_NULLABLE_MARK = "?"


@dataclass(frozen=True)
class TypeVocabulary:
    primitives: frozenset[str]
    collection_wrappers: frozenset[str]

    def is_collection(self, type_text: str) -> bool:
        text = type_text.rstrip(_NULLABLE_MARK)
        if text.endswith(_ARRAY_SUFFIX):
            return True
        return bare_type_name(text) in self.collection_wrappers

    def uml_type(self, type_text: str) -> str:
        """Collections become multiplicity notation: List<Foo> -> Foo[*]."""
        text = type_text.strip()
        if text.endswith(_ARRAY_SUFFIX):
            return text[:-len(_ARRAY_SUFFIX)] + _UML_MANY_SUFFIX
        wrapper = bare_type_name(text)
        if wrapper not in self.collection_wrappers:
            return text
        type_arguments = text[len(wrapper):]
        if type_arguments.startswith(TYPE_PARAMETERS_START) and type_arguments.endswith(_TYPE_PARAMETERS_END):
            inner = type_arguments[len(TYPE_PARAMETERS_START):-len(_TYPE_PARAMETERS_END)]
            return inner.strip() + _UML_MANY_SUFFIX
        return text

    def type_names(self, type_text: str) -> set[str]:
        """Capitalized, non-built-in names in a possibly generic/array type."""
        tokens = _TYPE_TEXT_SEPARATORS.split(type_text.rstrip(_NULLABLE_MARK))
        return {
            token for token in tokens
            if token and _TYPE_NAME.match(token) and token not in self.primitives
        }
