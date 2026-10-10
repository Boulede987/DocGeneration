"""PlantUML styling shared by every language; a language adds the colors of
its own stereotypes (record, struct...)."""

from dataclasses import dataclass

CLASS_BLOCK_OPEN = "skinparam class {"
BLOCK_CLOSE = "}"
HIDE_ATTRIBUTE_ICONS = "skinparam classAttributeIconSize 0"
NO_SHADOWS = "skinparam shadowing false"


@dataclass(frozen=True)
class StereotypeStyle:
    """stereotype None styles plain classes."""
    stereotype: str | None
    background: str
    border: str

    def lines(self) -> list[str]:
        suffix = f"<<{self.stereotype}>>" if self.stereotype else ""
        return [
            CLASS_BLOCK_OPEN,
            f"  BackgroundColor{suffix} {self.background}",
            f"  BorderColor{suffix} {self.border}",
            BLOCK_CLOSE,
        ]


_HEADER = [HIDE_ATTRIBUTE_ICONS, NO_SHADOWS, ""]
_BASE_STYLES = [
    StereotypeStyle("interface", "#D6EAF8", "#2E86C1"),
    StereotypeStyle("abstract", "#E8DAEF", "#8E44AD"),
    StereotypeStyle(None, "#D5F5E3", "#27AE60"),
]
STATIC_STYLE = StereotypeStyle("static", "#a7faa0", "#38d610")
ENUM_STYLE = StereotypeStyle("enum", "#F5B7B1", "#C0392B")


def skinparam_lines(kind_styles: list[StereotypeStyle], extra_styles: list[StereotypeStyle] | None = None) -> list[str]:
    """Order: interface, abstract, plain class, kind_styles, static,
    extra_styles, enum. The order is part of the output: reordering changes
    every generated file."""
    styles = _BASE_STYLES + kind_styles + [STATIC_STYLE] + (extra_styles or []) + [ENUM_STYLE]
    return _HEADER + [line for style in styles for line in style.lines()]
