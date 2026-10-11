"""The types a field holds, and how: ownership decides the relation's
strength, which is more faithful to Rust than visibility."""

from typing import TYPE_CHECKING

from .facts import HeldType, Ownership
from .syntax import NAMED_TYPE_NODES, PATH_SEPARATOR, display_text, field, named_children, node_text

if TYPE_CHECKING:
    from tree_sitter import Node

SHARING_WRAPPERS = frozenset({"Rc", "Arc", "Weak"})
COLLECTION_WRAPPERS = frozenset({
    "Vec", "VecDeque", "LinkedList", "BinaryHeap", "HashMap", "BTreeMap", "HashSet", "BTreeSet",
})
# Hold their argument the way the field holds them (Box<T> owns T).
PASS_THROUGH_WRAPPERS = frozenset({"Box", "Option", "Result", "Cell", "RefCell", "Mutex", "RwLock", "Cow", "Pin"})
STANDARD_WRAPPERS = SHARING_WRAPPERS | COLLECTION_WRAPPERS | PASS_THROUGH_WRAPPERS
# A function pointer or closure type calls its parameter types: it holds none.
FUNCTION_TYPE = "function_type"
REFERENCE_NODES = frozenset({"reference_type", "pointer_type"})
SEQUENCE_NODES = frozenset({"array_type", "slice_type"})
GENERIC_TYPE = "generic_type"


def _wrapper_name(wrapper: "Node") -> str:
    """'Box' for Box<T> and std::boxed::Box<T>."""
    return node_text(wrapper).split(PATH_SEPARATOR)[-1]


def _held_in_generic(generic: "Node", ownership: Ownership, is_collection: bool) -> list[HeldType]:
    """A standard wrapper is not held itself, it says how its arguments
    are held; a crate's own generic type is held, and so are its
    arguments."""
    wrapper = field(generic, "type")
    name = _wrapper_name(wrapper) if wrapper is not None else ""
    arguments = named_children(field(generic, "type_arguments"))
    if name not in STANDARD_WRAPPERS:
        own = _held_types_of(wrapper, ownership, is_collection) if wrapper is not None else []
        return own + _held_in(arguments, ownership, is_collection)
    argument_ownership = Ownership.SHARED if name in SHARING_WRAPPERS else ownership
    return _held_in(arguments, argument_ownership, is_collection or name in COLLECTION_WRAPPERS)


def _held_types_of(node: "Node", ownership: Ownership, is_collection: bool) -> list[HeldType]:
    """References (shared or mutable) and raw pointers make what they
    point to shared; arrays and slices mark many."""
    if node.type in NAMED_TYPE_NODES:
        return [HeldType(display_text(node), ownership, is_collection)]
    if node.type == FUNCTION_TYPE:
        return []
    if node.type in REFERENCE_NODES:
        return _held_in(named_children(node), Ownership.SHARED, is_collection)
    if node.type in SEQUENCE_NODES:
        element = field(node, "element")
        return _held_types_of(element, ownership, True) if element is not None else []
    if node.type == GENERIC_TYPE:
        return _held_in_generic(node, ownership, is_collection)
    return _held_in(named_children(node), ownership, is_collection)


def _held_in(nodes: list["Node"], ownership: Ownership, is_collection: bool) -> list[HeldType]:
    return [held for node in nodes for held in _held_types_of(node, ownership, is_collection)]


def held_types(type_node: "Node") -> list[HeldType]:
    """Every named type in a field's type (filtered later: only crate
    types become relations)."""
    return _held_types_of(type_node, Ownership.OWNED, False)
