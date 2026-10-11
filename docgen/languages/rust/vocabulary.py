"""Rust collection wrappers (drawn as Foo[*]) and stereotype colors."""

from docgen.core import style
from docgen.oo.vocabulary import TypeVocabulary

# Maps are left out: Value[*] would hide their keys.
NON_MAP_COLLECTIONS = frozenset({"Vec", "VecDeque", "LinkedList", "BinaryHeap", "HashSet", "BTreeSet"})

RUST_VOCABULARY = TypeVocabulary(primitives=frozenset(), collection_wrappers=NON_MAP_COLLECTIONS)

SKINPARAM_LINES = style.skinparam_lines([style.MODULE_STYLE])
