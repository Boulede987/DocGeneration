"""C# built-in types, collection wrappers, and stereotype colors."""

from docgen.core.style import StereotypeStyle
from docgen.oo.vocabulary import TypeVocabulary

PRIMITIVES = frozenset({
    "void", "bool", "int", "float", "double", "long", "short", "byte",
    "uint", "ulong", "ushort", "sbyte", "char", "decimal", "object",
    "string", "dynamic", "var",
    # single-letter generic params
    "T", "U", "V", "K", "TKey", "TValue", "TComponent", "TResult",
    # common BCL containers and types (not project classes)
    "List", "Dictionary", "HashSet", "Queue", "Stack", "Array",
    "IEnumerable", "IList", "ICollection", "IReadOnlyList", "IReadOnlyCollection",
    "Action", "Func", "Predicate", "Delegate", "EventHandler",
    "Task", "ValueTask", "Nullable",
    "Math", "Random",
    "Exception", "ArgumentException", "InvalidOperationException",
    "IDisposable", "IEquatable", "IComparable", "ICloneable",
    "StringBuilder", "Stream", "StreamReader", "StreamWriter",
    "Encoding", "File", "Directory", "Path",
    "JsonConvert", "JObject", "JArray",
    "Type", "Object", "Enum", "Attribute",
})

COLLECTION_WRAPPERS = frozenset({
    "List", "IList", "IEnumerable", "IReadOnlyList", "ICollection",
    "IReadOnlyCollection", "HashSet", "Queue", "Stack", "LinkedList",
    "ObservableCollection", "SortedSet", "SortedList", "ConcurrentBag",
    "ConcurrentQueue", "ConcurrentStack",
})

CSHARP_VOCABULARY = TypeVocabulary(primitives=PRIMITIVES, collection_wrappers=COLLECTION_WRAPPERS)

STRUCT_STYLE = StereotypeStyle("struct", "#FAD7A0", "#D68910")
