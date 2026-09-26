"""One source file's parsed diagram parts, and the per-file diagram writer.
Every language generator parses a file into a FileDiagram exactly once; the
per-file writer and the package views both consume it."""

from dataclasses import dataclass
from pathlib import Path

from .puml import namespace_block, wrap_document, write_file

BASE_DIAGRAM_DIR = "ClassDiagram"
BASE_FRAGMENT_DIR = "Fragments"
FULL_DIAGRAM_DIR = "ClassDiagram-Full"
FULL_FRAGMENT_DIR = "Fragments-Full"


@dataclass
class FileDiagram:
    """'package' is the file's grouping unit: a Java package or a C#
    namespace, None when the file declares none.

    Relation lines are 'Left <arrow> [multiplicity] Right' with simple
    names; name_packages maps each of those names to the package it
    resolves to (None = unknown, drawn outside any package)."""
    stem: str
    package: str | None
    decl_names: set[str]
    inner_lines: list[str]
    rels: list[str]          # inheritance / realization
    compose_rels: list[str]  # composition — strong enough for base views
    other_rels: list[str]    # association / dependency — full views only
    name_packages: dict[str, str | None]

    def base_rels(self) -> list[str]:
        return self.rels + self.compose_rels

    def full_rels(self) -> list[str]:
        return self.rels + self.compose_rels + self.other_rels

    def qualify_rels(self, rel_lines: list[str]) -> list[str]:
        """Rewrite both ends of each relation line to their fully-qualified
        name, so they land in the right package when emitted outside any
        namespace block."""
        return [self._qualify_rel(line) for line in rel_lines]

    def _qualify_rel(self, rel_line: str) -> str:
        tokens = rel_line.split(" ")
        tokens[0] = self.qualified_name(tokens[0])
        tokens[-1] = self.qualified_name(tokens[-1])
        return " ".join(tokens)

    def qualified_name(self, name: str) -> str:
        package = self.name_packages.get(name)
        return f"{package}.{name}" if package else name


def relation_ends(rel_line: str) -> tuple[str, str]:
    tokens = rel_line.split(" ")
    return tokens[0], tokens[-1]


@dataclass(frozen=True)
class FileOutputPaths:
    base: Path
    base_fragment: Path
    full: Path
    full_fragment: Path

    @classmethod
    def under(cls, out_base: Path, source_rel_path: Path) -> "FileOutputPaths":
        puml_rel_path = source_rel_path.with_suffix(".puml")
        return cls(
            base=out_base / BASE_DIAGRAM_DIR / puml_rel_path,
            base_fragment=out_base / BASE_FRAGMENT_DIR / puml_rel_path,
            full=out_base / FULL_DIAGRAM_DIR / puml_rel_path,
            full_fragment=out_base / FULL_FRAGMENT_DIR / puml_rel_path,
        )


def _file_body(fd: FileDiagram, rel_lines: list[str]) -> list[str]:
    """Fragment body: no @startuml, skinparam, or @enduml."""
    return namespace_block(fd.package, fd.inner_lines) + [""] + fd.qualify_rels(rel_lines)


def write_file_outputs(fd: FileDiagram, paths: FileOutputPaths, skinparam_lines: list[str]) -> None:
    base_body = _file_body(fd, fd.base_rels())
    write_file(paths.base, wrap_document(fd.stem, skinparam_lines, base_body))
    write_file(paths.base_fragment, base_body)

    full_body = _file_body(fd, fd.full_rels())
    write_file(paths.full, wrap_document(fd.stem, skinparam_lines, full_body))
    write_file(paths.full_fragment, full_body)
