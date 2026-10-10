import difflib
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = REPO_ROOT / "tests" / "fixtures"
GOLDEN = REPO_ROOT / "tests" / "golden"
OUTPUT_ENCODING = "utf-8"
SCRIPT_TIMEOUT_SECONDS = 120


def run_script(script: str, *args: object, cwd: Path) -> subprocess.CompletedProcess[str]:
    """Run one of the repo's entry scripts the way a user would. cwd should
    be a temporary folder: a script that misreads its arguments may write
    output relative to it."""
    return subprocess.run(
        [sys.executable, str(REPO_ROOT / script), *map(str, args)],
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding=OUTPUT_ENCODING,
        timeout=SCRIPT_TIMEOUT_SECONDS,
    )


def puml_files(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*.puml"))
    }


def _difference_report(relative_path: str, expected: bytes, actual: bytes) -> str:
    """A unified diff; when the texts only differ in line endings, say so
    instead of showing an empty diff."""
    diff = "".join(difflib.unified_diff(
        expected.decode(OUTPUT_ENCODING, errors="replace").splitlines(keepends=True),
        actual.decode(OUTPUT_ENCODING, errors="replace").splitlines(keepends=True),
        fromfile=f"golden/{relative_path}",
        tofile=f"actual/{relative_path}",
    ))
    return diff or f"{relative_path}: bytes differ (line endings or encoding)"


def assert_same_tree(actual_root: Path, expected_root: Path) -> None:
    """Every .puml file byte-identical, same set of files."""
    expected = puml_files(expected_root)
    assert expected, f"golden folder {expected_root} is missing or holds no .puml file"
    actual = puml_files(actual_root)
    missing = sorted(set(expected) - set(actual))
    extra = sorted(set(actual) - set(expected))
    assert not missing and not extra, f"missing: {missing}\nextra: {extra}"
    for relative_path, expected_bytes in expected.items():
        assert actual[relative_path] == expected_bytes, _difference_report(
            relative_path, expected_bytes, actual[relative_path],
        )
