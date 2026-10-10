"""Reading a declaration's modifier keywords (e.g. 'public static final')."""

from docgen.core.model import Visibility

VisibilityRules = list[tuple[str, Visibility]]


def visibility_from(modifiers: str, rules: VisibilityRules) -> Visibility:
    """First rule whose keyword occurs in the modifiers; PACKAGE otherwise.
    Rules are matched as substrings, so multi-word keywords ('private
    protected') must come before their parts."""
    for keyword, visibility in rules:
        if keyword in modifiers:
            return visibility
    return Visibility.PACKAGE


def has_modifier(modifiers: str, *keywords: str) -> bool:
    """Whole-word match: 'static' is not found in 'nonstatic'."""
    words = modifiers.split()
    return any(keyword in words for keyword in keywords)
