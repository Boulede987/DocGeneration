"""Unity is C# with engine conventions: engine base classes aren't drawn,
ScriptableObject assets are shared rather than owned, and [SerializeField]
fields are owned like public ones."""

from docgen.core import style
from docgen.core.model import bare_type_name
from docgen.core.project import Project
from docgen.core.relations import AGGREGATES, ASSOCIATES, COMPOSES, RelationLevel
from docgen.languages.csharp.declarations import TypeHeader
from docgen.languages.csharp.language import CSharpLanguage
from docgen.languages.csharp.vocabulary import COLLECTION_WRAPPERS, PRIMITIVES, STRUCT_STYLE
from docgen.oo.inference import FieldFacts, RelationPolicy
from docgen.oo.language import ObjectOrientedFacts
from docgen.oo.vocabulary import TypeVocabulary

SCRIPTABLE_OBJECT = "ScriptableObject"
UNITY_BASES = frozenset({"MonoBehaviour", SCRIPTABLE_OBJECT, "GameObject", "Component"})
UNITY_PRIMITIVES = PRIMITIVES | frozenset({
    "GameObject", "MonoBehaviour", "ScriptableObject", "Component",
    "Transform", "Vector2", "Vector3", "Vector4", "Quaternion",
    "Color", "Color32", "Rect", "RectTransform", "Sprite", "Texture2D",
    "Coroutine", "WaitForSeconds", "WaitUntil", "WaitForEndOfFrame",
    "UnityEvent", "SerializeField", "RequireComponent",
    "Debug", "Mathf", "Resources", "Addressables",
    "AssetReference", "AsyncOperationHandle",
})
SCRIPTABLE_OBJECT_STYLE = style.StereotypeStyle("scriptableObject", "#d6a0fa", "#d61094")
SCRIPTABLE_OBJECT_STEREOTYPE = f"<<{SCRIPTABLE_OBJECT_STYLE.stereotype}>>"


class UnityRelationPolicy(RelationPolicy):
    """Aggregation (o-->): a ScriptableObject-typed field — an asset shared
    across holders. Composition: instantiated, public, or [SerializeField]."""

    def __init__(self, scriptable_objects: set[str]) -> None:
        self.scriptable_objects = scriptable_objects

    def classify_field(self, facts: FieldFacts) -> tuple[str, RelationLevel]:
        if facts.target in self.scriptable_objects:
            return AGGREGATES, RelationLevel.WEAK
        if facts.is_newed or facts.is_public or facts.is_serialized:
            return COMPOSES, RelationLevel.STRONG
        return ASSOCIATES, RelationLevel.WEAK


def scriptable_object_subclasses(project: Project[ObjectOrientedFacts]) -> set[str]:
    """Every project type inheriting ScriptableObject, directly or not."""
    base_of = {
        type_facts.bare_name: bare_type_name(type_facts.base_class) if type_facts.base_class else None
        for parsed in project.files
        for type_facts in parsed.facts or []
    }
    found = {name for name, base in base_of.items() if base == SCRIPTABLE_OBJECT}
    newly_found = found
    while newly_found:
        newly_found = {name for name, base in base_of.items() if base in found and name not in found}
        found |= newly_found
    return found


class UnityLanguage(CSharpLanguage):
    name = "unity"
    skinparam_lines = style.skinparam_lines([STRUCT_STYLE], [SCRIPTABLE_OBJECT_STYLE])
    vocabulary = TypeVocabulary(primitives=UNITY_PRIMITIVES, collection_wrappers=COLLECTION_WRAPPERS)
    hidden_bases = UNITY_BASES

    def stereotype(self, header: TypeHeader, modifiers: frozenset[str]) -> str | None:
        """Only a direct ScriptableObject subclass is marked."""
        if header.base_class == SCRIPTABLE_OBJECT:
            return SCRIPTABLE_OBJECT_STEREOTYPE
        return super().stereotype(header, modifiers)

    def relation_policy(self, project: Project[ObjectOrientedFacts]) -> RelationPolicy:
        return UnityRelationPolicy(scriptable_object_subclasses(project))
