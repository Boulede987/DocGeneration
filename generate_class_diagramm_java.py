#!/usr/bin/env python3
"""
generate_class_diagramm_java.py
Reads every .java file under one or more <src_dir> trees and writes:
  Modelisation/ClassDiagram/    — one .puml per file, extends/implements only
  Modelisation/Fragments/       — fragment versions (no @startuml/@enduml)
  Modelisation/ClassDiagram-Full/ — same + --> (field) and ..> (method-only) to known types
  Modelisation/Fragments-Full/    — fragment versions of the full diagrams
  Modelisation/Packages/         — one aggregate diagram per Java package, plus
                                    an _overview.puml linking them by cross-package usage

Multiple <src_dir> trees are merged into a single known-types index and a
single Packages/ view — pass every module's source root (e.g. a Gradle
multi-module project) in one invocation so cross-module relationships and
the package overview are complete instead of only covering whichever
module was scanned last.
"""

import argparse
import sys
from pathlib import Path

from java_diagram.file_diagram import PACKAGE_RE, FileDiagram, build_file_diagram
from java_diagram.packages import generate_package_diagrams
from java_diagram.render import assemble, write_file
from java_diagram.source_parsing import find_type_decls, strip_comments, strip_strings


def _write_file_outputs(
    fd: FileDiagram,
    out_path: Path,
    frag_path: Path,
    full_out_path: Path,
    full_frag_path: Path,
) -> None:
    rels = fd.qualify_rels(fd.rels)
    compose_rels = fd.qualify_rels(fd.compose_rels)
    other_rels = fd.qualify_rels(fd.other_rels)

    base_all, base_body = assemble(fd.stem, fd.package, fd.inner_lines, rels, [])
    write_file(out_path, base_all)
    write_file(frag_path, base_body)

    if compose_rels:
        base_all, base_body = assemble(fd.stem, fd.package, fd.inner_lines, rels, compose_rels)
        write_file(out_path, base_all)
        write_file(frag_path, base_body)

    full_all, full_body = assemble(fd.stem, fd.package, fd.inner_lines, rels, compose_rels + other_rels)
    write_file(full_out_path, full_all)
    write_file(full_frag_path, full_body)


def generate_puml(
    java_path: Path,
    out_path: Path,
    frag_path: Path,
    full_out_path: Path,
    full_frag_path: Path,
    type_packages: dict[str, set[str | None]],
) -> bool:
    fd = build_file_diagram(java_path, type_packages)
    if fd is None:
        return False
    _write_file_outputs(fd, out_path, frag_path, full_out_path, full_frag_path)
    return True


# ── Entry point ───────────────────────────────────────────────────────────────

_STATUS_OK = "OK"
_STATUS_SKIPPED = "SKIPPED"
_STATUS_ERROR = "ERROR"


def _generate_one(
    java_file: Path,
    rel: Path,
    out_dirs: tuple[Path, Path, Path, Path],
    type_packages: dict[str, set[str | None]],
) -> tuple[str, FileDiagram | None]:
    """Build and write all diagram variants for one file. Returns a status
    string and the parsed FileDiagram (None on skip/error), prints the
    per-file result line."""
    out_root, frag_root, full_out_root, full_frag_root = out_dirs
    out = out_root / rel.with_suffix(".puml")
    frag = frag_root / rel.with_suffix(".puml")
    full_out = full_out_root / rel.with_suffix(".puml")
    full_frag = full_frag_root / rel.with_suffix(".puml")

    try:
        fd = build_file_diagram(java_file, type_packages)
        if fd is None:
            print(f"  SKIP   {rel}  (no type declarations)")
            return _STATUS_SKIPPED, None
        _write_file_outputs(fd, out, frag, full_out, full_frag)
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

    out_root = out_base / "ClassDiagram"
    frag_root = out_base / "Fragments"
    full_out_root = out_base / "ClassDiagram-Full"
    full_frag_root = out_base / "Fragments-Full"
    packages_root = out_base / "Packages"

    rel_by_file = _find_java_files(args.src_dirs)
    java_files = sorted(rel_by_file)
    print(f"Found {len(java_files)} .java files under {', '.join(str(r) for r in args.src_dirs)}")

    type_packages = _collect_type_packages(java_files)
    print(f"  {len(type_packages)} known project types for uses-detection")

    out_dirs = (out_root, frag_root, full_out_root, full_frag_root)
    file_diagrams: list[FileDiagram] = []
    results: list[str] = []
    for jf in java_files:
        status, fd = _generate_one(jf, rel_by_file[jf], out_dirs, type_packages)
        results.append(status)
        if fd is not None:
            file_diagrams.append(fd)

    ok = results.count(_STATUS_OK)
    skipped = results.count(_STATUS_SKIPPED)
    errors = results.count(_STATUS_ERROR)
    print(f"\nDone: {ok} generated, {skipped} skipped, {errors} errors.")

    package_count = generate_package_diagrams(file_diagrams, packages_root)
    print(f"Wrote {package_count} package diagrams + overview to {packages_root}")


if __name__ == "__main__":
    main()
