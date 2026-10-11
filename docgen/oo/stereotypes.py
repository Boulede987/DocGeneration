"""The stereotypes object-oriented languages share."""

ABSTRACT_MODIFIER = "abstract"
STATIC_MODIFIER = "static"
RECORD_STEREOTYPE = "<<record>>"
STRUCT_STEREOTYPE = "<<struct>>"
MODULE_STEREOTYPE = "<<module>>"
ABSTRACT_STEREOTYPE = "<<abstract>>"
STATIC_STEREOTYPE = "<<static>>"


def class_stereotype(modifiers: frozenset[str], kind_stereotype: str | None = None) -> str | None:
    """What the type is (record, struct...) wins over how it's declared
    (abstract, then static); None for a plain class."""
    if kind_stereotype is not None:
        return kind_stereotype
    if ABSTRACT_MODIFIER in modifiers:
        return ABSTRACT_STEREOTYPE
    if STATIC_MODIFIER in modifiers:
        return STATIC_STEREOTYPE
    return None


def is_abstract(modifiers: frozenset[str]) -> bool:
    return ABSTRACT_MODIFIER in modifiers
