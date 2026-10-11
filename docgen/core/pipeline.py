"""The run every language shares: find source files under one or more
roots, parse each once, let the language link the project (relations,
cross-file merges), write per-file diagrams, then the package views."""

from dataclasses import dataclass, field
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Mapping, Sequence

from .file_diagram import FileDiagram, FileOutputPaths, write_file_outputs
from .language import Language
from .model import ParsedFile, SourceText
from .package_views import generate_package_views
from .project import Project
from .relations import Relation
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
    excluded: int = 0
    notes: dict[Path, list[str]] = field(default_factory=dict)
    link_error: str | None = None  # the language failed to link: diagrams have no relations

    def record_error(self, source: SourceFile, error: Exception) -> None:
        self.errors[source.relative_path] = _error_text(error)

    @property
    def has_errors(self) -> bool:
        return bool(self.errors) or self.link_error is not None


def _error_text(error: Exception) -> str:
    return f"{type(error).__name__}: {error}"


CURRENT_FOLDER_PREFIX = "./"


def normalized_pattern(pattern: str) -> str:
    """Patterns are written against '/'-separated paths: 'tests\\*' and
    './tests/*' mean 'tests/*'."""
    pattern = pattern.replace("\\", "/")
    return pattern[len(CURRENT_FOLDER_PREFIX):] if pattern.startswith(CURRENT_FOLDER_PREFIX) else pattern


def _is_excluded(source: SourceFile, excludes: Sequence[str]) -> bool:
    """Case-sensitive on every platform, so a pattern means the same thing
    on Windows and Linux. '*' also crosses folders: 'tests/*' excludes
    everything under tests. Patterns match files, not folders."""
    text = source.relative_path.as_posix()
    return any(fnmatchcase(text, normalized_pattern(pattern)) for pattern in excludes)


def discover_sources(src_roots: Sequence[Path], suffix: str) -> list[SourceFile]:
    """Every file with the suffix under the roots, sorted by path. A file
    under nested roots is relative to the most specific one."""
    root_of: dict[Path, Path] = {}
    for root in src_roots:
        for path in root.rglob(f"*{suffix}"):
            current = root_of.get(path)
            if current is None or len(root.parts) > len(current.parts):
                root_of[path] = root
    return [SourceFile(path, path.relative_to(root_of[path])) for path in sorted(root_of)]


def build_file_diagram(
    parsed: ParsedFile,
    relations: list[Relation],
    index: ProjectIndex,
    language: Language,
) -> FileDiagram:
    """Relations are sorted by level, stably: within a level, the order the
    language gave is kept."""
    sorted_relations = sorted(relations, key=lambda relation: relation.level)
    names = {end for relation in sorted_relations for end in (relation.source, relation.target)}
    return FileDiagram(
        stem=parsed.stem,
        package=parsed.package,
        inner_lines=[line for declaration in parsed.declarations for line in render_declaration(declaration)],
        relations=sorted_relations,
        name_packages={
            name: resolve_package(name, parsed, index, language.enclosing_packages) for name in names
        },
    )


def _parse_source(language: Language, source: SourceFile) -> ParsedFile:
    text = source.path.read_text(encoding=SOURCE_ENCODING, errors="replace")
    return language.parse_file(SourceText(source.relative_path, text))


def _parse_sources(language: Language, sources: list[SourceFile], summary: RunSummary) -> dict[SourceFile, ParsedFile]:
    """Every file that parsed, declarations or not: a file may only extend
    types declared elsewhere. A file that fails is recorded in summary, and
    the run goes on."""
    parsed_files: dict[SourceFile, ParsedFile] = {}
    for source in sources:
        try:
            parsed_files[source] = _parse_source(language, source)
        except Exception as error:
            summary.record_error(source, error)
    return parsed_files


def _write_diagrams(
    language: Language,
    parsed_files: dict[SourceFile, ParsedFile],
    relations: Mapping[ParsedFile, list[Relation]],
    project: Project,
    output_base: Path,
    summary: RunSummary,
) -> list[FileDiagram]:
    """One diagram per file that declares something (after linking)."""
    file_diagrams: list[FileDiagram] = []
    for source, parsed in parsed_files.items():
        if not parsed.declarations:
            summary.skipped.append(source.relative_path)
            continue
        try:
            file_diagram = build_file_diagram(parsed, relations.get(parsed, []), project.index, language)
            write_file_outputs(file_diagram, FileOutputPaths.under(output_base, source.relative_path),
                               language.skinparam_lines)
        except Exception as error:
            summary.record_error(source, error)
            continue
        file_diagrams.append(file_diagram)
        summary.generated += 1
    return file_diagrams


def _link(language: Language, project: Project, summary: RunSummary) -> Mapping[ParsedFile, list[Relation]]:
    """A language that fails to link still gets its diagrams, without
    relations: the declarations are right, and the error is reported."""
    try:
        return language.link(project)
    except Exception as error:
        summary.link_error = _error_text(error)
        return {}


def run(language: Language, src_roots: Sequence[Path], output_base: Path, excludes: Sequence[str] = ()) -> RunSummary:
    """discover -> parse each file -> link the project -> write per-file
    diagrams -> write package views. The same for every language."""
    summary = RunSummary()
    discovered = discover_sources(src_roots, language.source_suffix)
    sources = [source for source in discovered if not _is_excluded(source, excludes)]
    summary.excluded = len(discovered) - len(sources)
    parsed_files = _parse_sources(language, sources, summary)
    project = Project(list(parsed_files.values()))
    relations = _link(language, project, summary)
    summary.notes = {source.relative_path: parsed.notes for source, parsed in parsed_files.items() if parsed.notes}

    file_diagrams = _write_diagrams(language, parsed_files, relations, project, output_base, summary)
    summary.package_count = generate_package_views(
        file_diagrams, output_base, language.views_dir, language.skinparam_lines,
    )
    return summary
