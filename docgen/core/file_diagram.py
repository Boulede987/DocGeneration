"""One source file's diagram parts, and the per-file diagram writer. Each
file is parsed into a FileDiagram exactly once."""

from dataclasses import dataclass
from pathlib import Path

from .puml import namespace_block, wrap_document, write_file
from .relations import Relation, RelationLevel

PUML_SUFFIX = ".puml"
BASE_DIAGRAM_DIR = "ClassDiagram"
BASE_FRAGMENT_DIR = "Fragments"
FULL_DIAGRAM_DIR = "ClassDiagram-Full"
FULL_FRAGMENT_DIR = "Fragments-Full"


@dataclass(frozen=True)
class EndPackages:
    """The package each end of a relation resolved to (None = unknown or
    no package, drawn outside any package)."""
    source: str | None
    target: str | None


def _qualified(name: str, package: str | None) -> str:
    return f"{package}.{name}" if package else name


@dataclass
class FileDiagram:
    """'package' is the file's grouping unit (None when it declares none).
    relations are sorted by level; end_packages gives, for each relation,
    where its ends are declared. Kept per relation, not per name: two
    targets may share a name in different packages."""
    stem: str
    package: str | None
    inner_lines: list[str]
    relations: list[Relation]
    end_packages: dict[Relation, EndPackages]

    def base_relations(self) -> list[Relation]:
        return [relation for relation in self.relations if relation.level <= RelationLevel.STRONG]

    def full_relations(self) -> list[Relation]:
        return list(self.relations)

    def target_package(self, relation: Relation) -> str | None:
        return self.end_packages[relation].target

    def qualified_source(self, relation: Relation) -> str:
        return _qualified(relation.source, self.end_packages[relation].source)

    def qualified_target(self, relation: Relation) -> str:
        return _qualified(relation.target, self.target_package(relation))

    def render_relations(self, relations: list[Relation]) -> list[str]:
        """Fully-qualified relation lines, so they land in the right package
        when emitted outside any namespace block."""
        return [
            relation.render(self.qualified_source(relation), self.qualified_target(relation))
            for relation in relations
        ]


@dataclass(frozen=True)
class FileOutputPaths:
    base: Path
    base_fragment: Path
    full: Path
    full_fragment: Path

    @classmethod
    def under(cls, output_base: Path, source_relative_path: Path) -> "FileOutputPaths":
        puml_relative_path = source_relative_path.with_suffix(PUML_SUFFIX)
        return cls(
            base=output_base / BASE_DIAGRAM_DIR / puml_relative_path,
            base_fragment=output_base / BASE_FRAGMENT_DIR / puml_relative_path,
            full=output_base / FULL_DIAGRAM_DIR / puml_relative_path,
            full_fragment=output_base / FULL_FRAGMENT_DIR / puml_relative_path,
        )


def _file_body(diagram: FileDiagram, relations: list[Relation]) -> list[str]:
    """Fragment body: no @startuml, skinparam, or @enduml."""
    return namespace_block(diagram.package, diagram.inner_lines) + [""] + diagram.render_relations(relations)


def write_file_outputs(diagram: FileDiagram, paths: FileOutputPaths, skinparam_lines: list[str]) -> None:
    base_body = _file_body(diagram, diagram.base_relations())
    write_file(paths.base, wrap_document(diagram.stem, skinparam_lines, base_body))
    write_file(paths.base_fragment, base_body)

    full_body = _file_body(diagram, diagram.full_relations())
    write_file(paths.full, wrap_document(diagram.stem, skinparam_lines, full_body))
    write_file(paths.full_fragment, full_body)
