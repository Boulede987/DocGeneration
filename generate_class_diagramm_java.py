#!/usr/bin/env python3
"""
generate_class_diagramm_java.py
Reads every .java file under one or more <src_dir> trees and writes:
  Modelisation/ClassDiagram/    — one .puml per file, extends/implements only
  Modelisation/Fragments/       — fragment versions (no @startuml/@enduml)
  Modelisation/ClassDiagram-Full/ — same + --> (field) and ..> (method-only) to known types
  Modelisation/Fragments-Full/    — fragment versions of the full diagrams
  Modelisation/Packages/         — one diagram per Java package, an _overview.puml
                                    linking them by cross-package usage, and a
                                    _project.puml with every class (base relations)
  Modelisation/Packages-Full/    — same views with every relation

Multiple <src_dir> trees are merged into a single known-types index and a
single set of Packages/ views — pass every module's source root (e.g. a Gradle
multi-module project) in one invocation so cross-module relationships and
the package overview are complete instead of only covering whichever
module was scanned last.
"""

import argparse
import sys
from pathlib import Path

from diagram_common.file_diagram import FileDiagram, FileOutputPaths, write_file_outputs
from diagram_common.package_views import generate_package_views
from java_diagram.file_diagram import PACKAGE_RE, build_file_diagram
from java_diagram.render import SKINPARAM_LINES
from java_diagram.source_parsing import find_type_decls, strip_comments, strip_strings

PACKAGE_VIEWS_DIR = "Packages"
_STATUS_OK = "OK"
_STATUS_SKIPPED = "SKIPPED"
_STATUS_ERROR = "ERROR"


def _generate_one(
    java_file: Path,
    rel: Path,
    out_base: Path,
    type_packages: dict[str, set[str | None]],
) -> tuple[str, FileDiagram | None]:
    """Build and write all diagram variants for one file. Returns a status
    string and the parsed FileDiagram (None on skip/error), prints the
    per-file result line."""
    try:
        fd = build_file_diagram(java_file, type_packages)
        if fd is None:
            print(f"  SKIP   {rel}  (no type declarations)")
            return _STATUS_SKIPPED, None
        write_file_outputs(fd, FileOutputPaths.under(out_base, rel), SKINPARAM_LINES)
        print(f"  OK     {rel}")
        return _STATUS_OK, fd
    except Exception as exc:
        print(f"  ERROR  {rel}  — {exc}")
        return _STATUS_ERROR, None


def _collect_type_packages(java_files: list[Path]) -> dict[str, set[str | None]]:
    """Simple name -> package(s) declaring it, for every project type. A
    name maps to several packages when unrelated packages reuse it."""
    type_packages: dict[str, set[str | None]] = {}
    for jf in java_files:
        try:
            raw = jf.read_text(encoding="utf-8", errors="replace")
            src = strip_strings(strip_comments(raw))
            pkg_m = PACKAGE_RE.search(src)
            package = pkg_m.group(1) if pkg_m else None
            for d in find_type_decls(src):
                type_packages.setdefault(d["name"].split("<")[0], set()).add(package)
        except Exception:
            pass
    return type_packages


def _find_java_files(src_roots: list[Path]) -> dict[Path, Path]:
    """Map each discovered .java file to its path relative to whichever
    src_root contains it (the longest/most specific match, in case roots
    happen to nest)."""
    files_to_root: dict[Path, Path] = {}
    for root in src_roots:
        for jf in root.rglob("*.java"):
            current_root = files_to_root.get(jf)
            if current_root is None or len(root.parts) > len(current_root.parts):
                files_to_root[jf] = root
    return {jf: jf.relative_to(root) for jf, root in files_to_root.items()}


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate PlantUML class diagrams from Java source.",
    )
    parser.add_argument(
        "src_dirs", nargs="+", type=Path,
        help="one or more directories to search recursively for .java files "
             "(pass every module's source root together for a complete Packages/ view)",
    )
    parser.add_argument(
        "-o", "--out", type=Path, default=None,
        help="output root (default: <first src_dir>/Modelisation)",
    )
    return parser.parse_args(argv)


def main() -> None:
    args = _parse_args(sys.argv[1:])
    out_base = args.out if args.out is not None else args.src_dirs[0] / "Modelisation"

    rel_by_file = _find_java_files(args.src_dirs)
    java_files = sorted(rel_by_file)
    print(f"Found {len(java_files)} .java files under {', '.join(str(r) for r in args.src_dirs)}")

    type_packages = _collect_type_packages(java_files)
    print(f"  {len(type_packages)} known project types for uses-detection")

    file_diagrams: list[FileDiagram] = []
    results: list[str] = []
    for jf in java_files:
        status, fd = _generate_one(jf, rel_by_file[jf], out_base, type_packages)
        results.append(status)
        if fd is not None:
            file_diagrams.append(fd)

    ok = results.count(_STATUS_OK)
    skipped = results.count(_STATUS_SKIPPED)
    errors = results.count(_STATUS_ERROR)
    print(f"\nDone: {ok} generated, {skipped} skipped, {errors} errors.")

    package_count = generate_package_views(file_diagrams, out_base, PACKAGE_VIEWS_DIR, SKINPARAM_LINES)
    print(f"Wrote {package_count} package diagrams + overview + project views to {out_base / PACKAGE_VIEWS_DIR}(-Full)")


if __name__ == "__main__":
    main()
