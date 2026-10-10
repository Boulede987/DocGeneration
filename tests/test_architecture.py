"""Structural requirements from .claude/workflow/refactor/NEEDS.md: shared
pipeline, extensibility through the public Language interface, no private
cross-module imports, no oversized modules, one CLI style."""

import ast
import subprocess
from pathlib import Path

import pytest

from conftest import REPO_ROOT, run_script

MAX_MODULE_LINES = 300
OUT_OF_SCOPE = {"generate_mcd.py", "generate_mld.py"}
ENTRY_SCRIPTS = [
    "generate_class_diagramm_java.py", "generate_class_diagramm.py",
    "generate_class_diagramm_unity.py", "generate_class_diagramm_python.py",
]
PRIVATE_PREFIX = "_"
TOY_SOURCE = "package zoo\nclass Dog extends Animal\n  field owner: Person\nclass Person\n"
TOY_VIEWS_DIR = "Modules"
FULL_SUFFIX = "-Full"
FULL_DIAGRAM_DIR = "ClassDiagram-Full"


def _source_modules() -> list[Path]:
    """Python files git knows about (tracked or not ignored) that still
    exist, so local virtual environments or build folders never count."""
    listed = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "*.py"],
        cwd=REPO_ROOT, capture_output=True, text=True, check=True,
    ).stdout.split()
    return [
        REPO_ROOT / name for name in listed
        if not name.startswith("tests/") and Path(name).name not in OUT_OF_SCOPE and (REPO_ROOT / name).is_file()
    ]


def _private_imports(tree: ast.AST) -> list[str]:
    """'from m import _x' and 'from m._private import x' (any private
    segment in the imported module path)."""
    offenders = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom):
            continue
        segments = (node.module or "").split(".")
        names = [alias.name for alias in node.names]
        if any(name.startswith(PRIVATE_PREFIX) for name in names + segments if name != "__future__"):
            offenders.append(f"from {node.module} import {', '.join(names)}")
    return offenders


@pytest.fixture(scope="module")
def toy_output(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Runs the toy language through the shared pipeline once."""
    from docgen.core.pipeline import run
    from toy_language import ToyLanguage

    workspace = tmp_path_factory.mktemp("toy")
    source_root = workspace / "src"
    source_root.mkdir()
    (source_root / "dog.toy").write_text(TOY_SOURCE, encoding="utf-8")
    output_base = workspace / "out"
    run(ToyLanguage(), [source_root], output_base)
    return output_base


def _toy_full_diagram(toy_output: Path) -> str:
    return (toy_output / FULL_DIAGRAM_DIR / "dog.puml").read_text(encoding="utf-8")


def test_registry_provides_every_supported_language():
    from docgen.languages import REGISTRY

    assert {"java", "csharp", "unity", "python"} <= set(REGISTRY)


def test_every_registered_language_implements_the_language_interface():
    from docgen.core.language import Language
    from docgen.languages import REGISTRY

    offenders = [name for name, language in REGISTRY.items() if not isinstance(language, Language)]

    assert REGISTRY and offenders == []


def test_new_language_types_are_drawn_inside_their_package(toy_output: Path):
    full = _toy_full_diagram(toy_output)

    assert "namespace zoo {" in full
    assert "class Dog {" in full


def test_new_language_inheritance_to_unknown_type_stays_outside_packages(toy_output: Path):
    assert "zoo.Dog --|> Animal" in _toy_full_diagram(toy_output)


def test_new_language_field_becomes_a_qualified_association(toy_output: Path):
    assert "zoo.Dog --> zoo.Person" in _toy_full_diagram(toy_output)


def test_new_language_gets_base_and_full_package_views(toy_output: Path):
    assert (toy_output / TOY_VIEWS_DIR / "_project.puml").is_file()
    assert (toy_output / f"{TOY_VIEWS_DIR}{FULL_SUFFIX}" / "_overview.puml").is_file()


def test_no_module_imports_private_names_from_another_module():
    offenders = {
        str(path.relative_to(REPO_ROOT)): found
        for path in _source_modules()
        if (found := _private_imports(ast.parse(path.read_text(encoding="utf-8"))))
    }

    assert offenders == {}


def test_no_module_exceeds_the_size_limit():
    oversized = {
        str(path.relative_to(REPO_ROOT)): line_count
        for path in _source_modules()
        if (line_count := len(path.read_text(encoding="utf-8").splitlines())) > MAX_MODULE_LINES
    }

    assert oversized == {}


@pytest.mark.parametrize("script", ENTRY_SCRIPTS)
def test_every_entry_script_offers_several_roots_and_an_out_option(script: str, tmp_path: Path):
    result = run_script(script, "--help", cwd=tmp_path)

    assert result.returncode == 0, result.stderr
    assert "src_dirs [src_dirs ...]" in result.stdout
    assert "[-o OUT]" in result.stdout  # usage line: the short option exists
    assert "--out OUT" in result.stdout


def test_adding_a_language_guide_exists_and_covers_registration():
    guide = REPO_ROOT / "docs" / "ADDING_A_LANGUAGE.md"

    assert guide.is_file()
    assert "REGISTRY" in guide.read_text(encoding="utf-8")
