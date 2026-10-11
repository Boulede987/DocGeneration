"""The command line every entry script shares:
    <script> SRC_DIR [SRC_DIR ...] [-o OUT]
Scripts that historically took 'SRC_DIR [OUT_DIR]' keep accepting it."""

import argparse
import io
import sys
from dataclasses import dataclass
from pathlib import Path

from .language import Language
from .pipeline import RunSummary, run

DEFAULT_OUT_DIR = "Modelisation"
LEGACY_PATH_COUNT = 2  # SRC_DIR OUT_DIR
EXIT_OK = 0
EXIT_ERRORS = 1
CONSOLE_ENCODING = "utf-8"


@dataclass(frozen=True)
class CommandLine:
    src_dirs: tuple[Path, ...]
    output_base: Path
    excludes: tuple[str, ...]


def _exclude_pattern(text: str) -> str:
    """A blank pattern would silently exclude nothing."""
    if not text.strip():
        raise argparse.ArgumentTypeError("--exclude needs a non-blank glob pattern")
    return text


def _parser(language: Language) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=f"Generate PlantUML class diagrams from {language.name} source.",
    )
    parser.add_argument(
        "src_dirs", nargs="+", type=Path,
        help=f"one or more directories to search recursively for {language.source_suffix} files "
             f"(pass every module's source root together for complete {language.views_dir}/ views)",
    )
    parser.add_argument(
        "-o", "--out", type=Path, default=None,
        help=f"output root (default: <first src_dir>/{DEFAULT_OUT_DIR})",
    )
    parser.add_argument(
        "--exclude", action="append", default=[], metavar="GLOB", type=_exclude_pattern,
        help="skip source files whose path relative to their src_dir matches GLOB "
             "(repeatable; e.g. --exclude 'tests/*')",
    )
    return parser


def _has_sources(path: Path, suffix: str) -> bool:
    return path.is_dir() and any(path.rglob(f"*{suffix}"))


def _split_legacy_out(src_dirs: list[Path], language: Language) -> tuple[list[Path], Path | None]:
    """'SRC_DIR OUT_DIR' (no -o): the second path is the output folder when
    it holds no source files — a source root always holds some. A missing
    second path counts as an output folder, created on write."""
    if len(src_dirs) != LEGACY_PATH_COUNT or _has_sources(src_dirs[1], language.source_suffix):
        return src_dirs, None
    print(f"Note: treating '{src_dirs[1]}' as the output folder (legacy form); prefer -o {src_dirs[1]}")
    return src_dirs[:1], src_dirs[1]


def parse_command_line(language: Language, argv: list[str], legacy_out_positional: bool) -> CommandLine:
    """Exits with a usage error when a source root is not a directory."""
    parser = _parser(language)
    arguments = parser.parse_args(argv)
    src_dirs, output_base = arguments.src_dirs, arguments.out
    if legacy_out_positional and output_base is None:
        src_dirs, output_base = _split_legacy_out(src_dirs, language)
    missing = [str(path) for path in src_dirs if not path.is_dir()]
    if missing:
        parser.error(f"source directory not found: {', '.join(missing)}")
    resolved_output_base = output_base if output_base is not None else src_dirs[0] / DEFAULT_OUT_DIR
    excludes: list[str] = arguments.exclude
    return CommandLine(tuple(src_dirs), resolved_output_base, tuple(excludes))


def _use_utf8_console() -> None:
    """Windows consoles default to a legacy code page that can't print
    every character of a source path or message."""
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(encoding=CONSOLE_ENCODING)


def _print_summary(summary: RunSummary, output_base: Path, views_dir: str) -> None:
    for relative_path in summary.skipped:
        print(f"  SKIP   {relative_path}  (no type declarations)")
    for relative_path, notes in summary.notes.items():
        for note in notes:
            print(f"  NOTE   {relative_path}  — {note}")
    for relative_path, message in summary.errors.items():
        print(f"  ERROR  {relative_path}  — {message}")
    if summary.link_error is not None:
        print(f"  ERROR  linking the project (diagrams drawn without relations) — {summary.link_error}")
    print(f"\nDone: {summary.generated} generated, {len(summary.skipped)} skipped, "
          f"{summary.excluded} excluded, {len(summary.errors)} errors.")
    print(f"Wrote {summary.package_count} package diagrams + overview + project views "
          f"to {output_base / views_dir}(-Full)")


def main(language: Language, argv: list[str] | None = None, legacy_out_positional: bool = False) -> int:
    """Returns the process exit code: non-zero when any file or the linking
    failed."""
    _use_utf8_console()
    command_line = parse_command_line(language, sys.argv[1:] if argv is None else argv, legacy_out_positional)
    excluding = f" (excluding {', '.join(command_line.excludes)})" if command_line.excludes else ""
    print(f"Reading {language.source_suffix} files under {', '.join(map(str, command_line.src_dirs))}{excluding}")
    summary = run(language, command_line.src_dirs, command_line.output_base, command_line.excludes)
    _print_summary(summary, command_line.output_base, language.views_dir)
    return EXIT_ERRORS if summary.has_errors else EXIT_OK
