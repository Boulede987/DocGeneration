"""Language-agnostic PlantUML text assembly and file writing, shared by the
Java, C# and Unity class diagram generators."""

from pathlib import Path


def namespace_block(package: str | None, inner_lines: list[str]) -> list[str]:
    """Wrap declarations in a 'namespace' block, or leave them at top level
    when there is no package. Only declarations belong inside: a relation
    line inside the block would create its undeclared targets in this
    package, even when they belong to another one."""
    if not package:
        return list(inner_lines)
    return [f"namespace {package} {{"] + inner_lines + ["}"]


def wrap_document(name: str, skinparam_lines: list[str], body: list[str]) -> list[str]:
    return [f"@startuml {name}", ""] + skinparam_lines + [""] + body + ["", "@enduml"]


def write_file(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
