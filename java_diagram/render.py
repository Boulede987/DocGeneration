"""Render parsed Java type declarations as PlantUML text: enum/interface
bodies, class stereotypes, the skinparam theme, and final @startuml assembly."""

import re
from pathlib import Path

from .depth_utils import split_top_level
from .members import ANNOT_PREFIX, flatten, has, simplify_params


def puml_name(name: str) -> str:
    """Strip generic parameters from a type name for relationship lines.
    PlantUML registers 'class Foo<T>' as 'Foo', so all cross-file references
    must use the bare name — otherwise !include linking breaks."""
    return name.split("<")[0]


SKINPARAM_LINES = [
    "skinparam classAttributeIconSize 0",
    "skinparam shadowing false",
    "",
    "skinparam class {",
    "  BackgroundColor<<interface>> #D6EAF8",
    "  BorderColor<<interface>> #2E86C1",
    "}",
    "skinparam class {",
    "  BackgroundColor<<abstract>> #E8DAEF",
    "  BorderColor<<abstract>> #8E44AD",
    "}",
    "skinparam class {",
    "  BackgroundColor #D5F5E3",
    "  BorderColor #27AE60",
    "}",
    "skinparam class {",
    "  BackgroundColor<<record>> #FCF3CF",
    "  BorderColor<<record>> #B7950B",
    "}",
    "skinparam class {",
    "  BackgroundColor<<static>> #a7faa0",
    "  BorderColor<<static>> #38d610",
    "}",
    "skinparam class {",
    "  BackgroundColor<<enum>> #F5B7B1",
    "  BorderColor<<enum>> #C0392B",
    "}",
]


def gen_enum(name: str, body: str, lines: list[str]):
    const_part, _rest = split_top_level(body, ";")
    const_part = re.sub(r"@\w+(?:\([^)]*\))?", "", const_part)   # strip annotations
    const_part = re.sub(r"\([^()]*\)", "", const_part)           # strip ctor args
    const_part = re.sub(r"\{[^{}]*\}", "", const_part)           # strip anon bodies
    values = [
        v.strip()
        for v in const_part.split(",")
        if v.strip() and re.match(r"^\w+$", v.strip())
    ]
    lines.append(f"enum {name} <<enum>> {{")
    for v in values:
        lines.append(f"  {v}")
    lines.append("}")


def gen_interface(name: str, body: str, lines: list[str]):
    lines.append(f"interface {name} <<interface>> {{")
    for stmt in flatten(body):
        stmt = ANNOT_PREFIX.sub("", stmt).strip()
        stmt = re.sub(r"\s*\{[^{}]*\}$", "", stmt)
        stmt = re.sub(r"^(?:(?:public|abstract|default|static|final)\s+)+", "", stmt)
        if not stmt:
            continue
        # Method
        m = re.match(r"([\w<>\[\],\.\? ]+)\s+(\w+)\s*(?:<[^>]+>)?\s*\(([^)]*)\)", stmt)
        if m:
            lines.append(f"  + {m.group(2)}({simplify_params(m.group(3))}) : {m.group(1)}")
            continue
        # Constant field
        if stmt.endswith(";"):
            m = re.match(r"([\w<>\[\],\.\? ]+)\s+(\w+)", stmt)
            if m:
                lines.append(f"  + {{static}} {m.group(2)} : {m.group(1)}")
    lines.append("}")


def class_stereotype(mods: str, kind: str) -> str:
    if kind == "record":
        return "<<record>>"
    if has(mods, "abstract"):
        return "<<abstract>>"
    if has(mods, "static"):
        return "<<static>>"
    return ""


def assemble(
    stem: str,
    package: str | None,
    inner_lines: list[str],
    rels: list[str],
    extra_rels: list[str],
) -> tuple[list[str], list[str]]:
    """Returns (full_lines, body_lines).
    body_lines has no @startuml, skinparam, or @enduml — for use as fragment.

    Relation lines go after the namespace block and must use fully-qualified
    names: inside the block, PlantUML creates every undeclared target in
    this file's package, even when it belongs to another one."""
    body: list[str] = []
    if package:
        body.append(f"namespace {package} {{")
    body.extend(inner_lines)
    if package:
        body.append("}")
    body.append("")
    body.extend(rels)
    if extra_rels:
        body.extend(extra_rels)

    full = [f"@startuml {stem}", ""] + SKINPARAM_LINES + [""] + body + ["", "@enduml"]
    return full, body


def write_file(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
