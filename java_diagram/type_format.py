"""Java type-string formatting for PlantUML: collection types become
multiplicity notation (List<Foo> -> Foo[*]) instead of showing the wrapper."""

COLLECTION_WRAPPERS = frozenset({
    "List", "ArrayList", "LinkedList", "Vector", "Stack",
    "Set", "HashSet", "LinkedHashSet", "TreeSet", "SortedSet", "NavigableSet",
    "Collection", "Queue", "Deque", "ArrayDeque", "PriorityQueue",
    "BlockingQueue", "ConcurrentLinkedQueue", "ConcurrentLinkedDeque",
    "CopyOnWriteArrayList", "CopyOnWriteArraySet",
})


def is_collection_type(type_str: str) -> bool:
    t = type_str.rstrip("?")
    if t.endswith("[]"):
        return True
    return t.split("<")[0] in COLLECTION_WRAPPERS


def uml_type(type_str: str) -> str:
    """Convert Java collection types to UML multiplicity notation."""
    t = type_str.strip()
    if t.endswith("[]"):
        return t[:-2] + "[*]"
    wrapper = t.split("<")[0]
    if wrapper in COLLECTION_WRAPPERS:
        inner = t[len(wrapper):]
        if inner.startswith("<") and inner.endswith(">"):
            return inner[1:-1].strip() + "[*]"
    return t
