"""Java built-in types, collection wrappers, and stereotype colors."""

from docgen.core import style
from docgen.oo.vocabulary import TypeVocabulary

PRIMITIVES = frozenset({
    "void", "boolean", "int", "byte", "short", "long", "float", "double", "char",
    "Object", "String", "var",
    # single-letter/common generic params
    "T", "U", "V", "K", "E", "R", "S",
    # common JDK containers and types (not project classes)
    "List", "ArrayList", "LinkedList", "Vector", "Stack",
    "Map", "HashMap", "TreeMap", "LinkedHashMap", "ConcurrentHashMap",
    "Set", "HashSet", "TreeSet", "LinkedHashSet",
    "Queue", "Deque", "ArrayDeque", "PriorityQueue",
    "Collection", "Collections", "Iterable", "Iterator", "Optional",
    "Stream", "IntStream", "LongStream", "DoubleStream", "Collectors",
    "Comparator", "Comparable", "Function", "BiFunction", "Consumer",
    "BiConsumer", "Supplier", "Predicate", "Runnable", "Callable", "Thread",
    "Exception", "RuntimeException", "IllegalArgumentException",
    "IllegalStateException", "IOException", "NullPointerException",
    "Objects", "Arrays", "Math", "StringBuilder", "StringBuffer",
    "Pattern", "Matcher", "Class", "Enum", "Record",
    "Number", "Integer", "Long", "Double", "Float", "Boolean", "Character",
    "Byte", "Short", "Void", "System",
    "Serializable", "Cloneable", "AutoCloseable", "Closeable",
    "Override", "Deprecated", "SuppressWarnings", "FunctionalInterface",
})

COLLECTION_WRAPPERS = frozenset({
    "List", "ArrayList", "LinkedList", "Vector", "Stack",
    "Set", "HashSet", "LinkedHashSet", "TreeSet", "SortedSet", "NavigableSet",
    "Collection", "Queue", "Deque", "ArrayDeque", "PriorityQueue",
    "BlockingQueue", "ConcurrentLinkedQueue", "ConcurrentLinkedDeque",
    "CopyOnWriteArrayList", "CopyOnWriteArraySet",
})

JAVA_VOCABULARY = TypeVocabulary(primitives=PRIMITIVES, collection_wrappers=COLLECTION_WRAPPERS)

SKINPARAM_LINES = style.skinparam_lines([style.StereotypeStyle("record", "#FCF3CF", "#B7950B")])
