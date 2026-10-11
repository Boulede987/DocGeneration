"""Python built-in and typing names, collection wrappers, stereotype colors."""

from docgen.core import style
from docgen.oo.vocabulary import TypeVocabulary

PRIMITIVES = frozenset({
    "None", "True", "False", "Ellipsis", "NotImplemented",
    # typing constructs (lowercase builtins like int/str never look like class names)
    "Any", "Optional", "Union", "Callable", "Literal", "Final", "ClassVar", "Annotated",
    "Self", "Type", "TypeVar", "TypeAlias", "NoReturn", "Never", "Protocol", "Generic",
    "List", "Dict", "Set", "FrozenSet", "Tuple", "Deque", "DefaultDict", "OrderedDict", "Counter",
    "Iterable", "Iterator", "Sequence", "MutableSequence", "Mapping", "MutableMapping",
    "Collection", "AbstractSet", "Generator", "AsyncIterator", "AsyncGenerator",
    "Awaitable", "Coroutine", "ContextManager", "Hashable", "Sized",
    # common single-letter type variables
    "T", "K", "V", "U", "R",
    # standard library classes that are never project classes
    "Path", "Enum", "IntEnum", "StrEnum", "Flag", "IntFlag", "ABC", "ABCMeta",
    "Exception", "ValueError", "TypeError", "KeyError", "RuntimeError", "NotImplementedError",
    "Decimal", "Fraction", "UUID", "Pattern", "Match",
})

COLLECTION_WRAPPERS = frozenset({
    "list", "List", "set", "Set", "frozenset", "FrozenSet", "deque", "Deque",
    "Sequence", "MutableSequence", "Iterable", "Iterator", "Collection", "AbstractSet",
})

PYTHON_VOCABULARY = TypeVocabulary(
    primitives=PRIMITIVES,
    collection_wrappers=COLLECTION_WRAPPERS,
    type_argument_brackets=("[", "]"),
)

DATACLASS_STYLE = style.StereotypeStyle("dataclass", "#FCF3CF", "#B7950B")
SKINPARAM_LINES = style.skinparam_lines([DATACLASS_STYLE, style.MODULE_STYLE])
