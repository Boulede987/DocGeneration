"""The run every language shares: find source files under one or more
roots, parse each once, index the project's types, write per-file diagrams,
then the package views."""

from dataclasses import dataclass, field
from pathlib import Path

from .file_diagram import FileDiagram, FileOutputPaths, write_file_outputs
from .language import Language
from .model import ParsedFile
from .package_views import generate_package_views
from .relations import Relation, RelationPolicy, inheritance_relations, inherited_names, usage_relations
from .render import render_declaration
from .resolution import ProjectIndex, resolve_package

SOURCE_ENCODING = "utf-8"


@dataclass(frozen=True)
class SourceFile:
    path: Path
    relative_path: Path  # relative to the source root containing it


@dataclass
class RunSummary:
    generated: int = 0
    skipped: list[Path] = field(default_factory=list)
    errors: dict[Path, str] = field(default_factory=dict)
    package_count: int = 0

    def record_error(self, source: SourceFile, error: Exception) -> None:
        self.errors[source.relative_path] = f"{type(error).__name__}: {error}"


def discover_sources(src_roots: list[Path], suffix: str) -> list[SourceFile]:
    """Every file with the suffix under the roots, sorted by path. A file
    under nested roots is relative to the most specific one."""
    root_of: dict[Path, Path] = {}
    for root in src_roots:
        for path in root.rglob(f"*{suffix}"):
            current = root_of.get(path)
            if current is None or len(root.parts) > len(current.parts):
                root_of[path] = root
    return [SourceFile(path, path.relative_to(root_of[path])) for path in sorted(root_of)]


def _relations_of(
    parsed: ParsedFile,
    known_types: set[str],
    language: Language,
    policy: RelationPolicy,
) -> list[Relation]:
    """Sorted by level, stable: within a level, declaration order is kept."""
    declarations = parsed.declarations
    inheritance = [
        relation
        for declaration in declarations
        for relation in inheritance_relations(declaration, language.hidden_bases)
    ]
    usages = [
        relation
        for declaration in declarations
        for relation in usage_relations(
            declaration, known_types, inherited_names(declaration), policy, language.vocabulary,
        )
    ]
    return sorted(inheritance + usages, key=lambda relation: relation.level)


def build_file_diagram(
    parsed: ParsedFile,
    index: ProjectIndex,
    language: Language,
    policy: RelationPolicy,
) -> FileDiagram:
    relations = _relations_of(parsed, index.known_types(), language, policy)
    names = {end for relation in relations for end in (relation.source, relation.target)}
    return FileDiagram(
        stem=parsed.stem,
        package=parsed.package,
        inner_lines=[
            line
            for declaration in parsed.declarations
            for line in render_declaration(declaration, language.class_stereotype(declaration))
        ],
        relations=relations,
        name_packages={
            name: resolve_package(name, parsed, index, language.enclosing_packages) for name in names
        },
    )


def _parse_source(language: Language, source: SourceFile) -> ParsedFile:
    text = source.path.read_text(encoding=SOURCE_ENCODING, errors="replace")
    return language.parse_file(source.path.stem, text)


def _parse_sources(language: Language, sources: list[SourceFile], summary: RunSummary) -> dict[SourceFile, ParsedFile]:
    """Parsed files with at least one declaration. A file that fails or
    declares nothing is recorded in summary, and the run goes on."""
    parsed_files: dict[SourceFile, ParsedFile] = {}
    for source in sources:
        try:
            parsed = _parse_source(language, source)
        except Exception as error:
            summary.record_error(source, error)
            continue
        if parsed.declarations:
            parsed_files[source] = parsed
        else:
            summary.skipped.append(source.relative_path)
    return parsed_files


def run(language: Language, src_roots: list[Path], output_base: Path) -> RunSummary:
    summary = RunSummary()
    parsed_files = _parse_sources(language, discover_sources(src_roots, language.source_suffix), summary)
    index = ProjectIndex(list(parsed_files.values()))
    policy = language.relation_policy(list(parsed_files.values()))

    file_diagrams: list[FileDiagram] = []
    for source, parsed in parsed_files.items():
        try:
            file_diagram = build_file_diagram(parsed, index, language, policy)
            write_file_outputs(file_diagram, FileOutputPaths.under(output_base, source.relative_path),
                               language.skinparam_lines)
        except Exception as error:
            summary.record_error(source, error)
            continue
        file_diagrams.append(file_diagram)
        summary.generated += 1

    summary.package_count = generate_package_views(
        file_diagrams, output_base, language.views_dir, language.skinparam_lines,
    )
    return summary
