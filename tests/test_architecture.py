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
TOY_SOURCE = "package zoo\nclass Dog extends Animal\n  field owner: Person\nclass Person\nclass Collar\n"
# In another file: adds a field to Dog, and tries to extend a class that doesn't exist.
TOY_EXTENSION_SOURCE = "extend Dog\n  field collar: Collar\nextend Ghost\n  field name: str\n"
CORE_DIR = REPO_ROOT / "docgen" / "core"
UML_KINDS = {"CLASS", "INTERFACE", "ENUM"}
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
def toy_run(tmp_path_factory: pytest.TempPathFactory):
    """Runs the toy language through the shared pipeline once:
    (output folder, run summary)."""
    from docgen.core.pipeline import run
    from toy_language import ToyLanguage

    workspace = tmp_path_factory.mktemp("toy")
    source_root = workspace / "src"
    source_root.mkdir()
    (source_root / "dog.toy").write_text(TOY_SOURCE, encoding="utf-8")
    (source_root / "extras.toy").write_text(TOY_EXTENSION_SOURCE, encoding="utf-8")
    output_base = workspace / "out"
    summary = run(ToyLanguage(), [source_root], output_base)
    return output_base, summary


@pytest.fixture(scope="module")
def toy_output(toy_run) -> Path:
    return toy_run[0]


def _core_imports() -> list[str]:
    """Every module imported by docgen/core."""
    imported = []
    for path in CORE_DIR.glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ImportFrom) and node.module:
                imported.append(node.module)
            elif isinstance(node, ast.Import):
                imported.extend(alias.name for alias in node.names)
    return imported


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
    assert "class Dog <<toy>> {" in full


def test_new_language_inheritance_to_unknown_type_stays_outside_packages(toy_output: Path):
    assert "zoo.Dog --|> Animal" in _toy_full_diagram(toy_output)


def test_new_language_field_becomes_a_qualified_association(toy_output: Path):
    assert "zoo.Dog --> zoo.Person" in _toy_full_diagram(toy_output)


def test_new_language_can_merge_a_declaration_across_files(toy_output: Path):
    full = _toy_full_diagram(toy_output)

    assert "  - collar : Collar" in full
    assert "zoo.Dog --> zoo.Collar" in full


def test_new_language_notes_are_reported_without_failing_the_run(toy_run):
    _output, summary = toy_run

    assert summary.errors == {}
    assert any("Ghost" in note for notes in summary.notes.values() for note in notes)


def test_a_failing_link_is_reported_and_diagrams_are_still_written(tmp_path: Path):
    from docgen.core.pipeline import run
    from toy_language import ToyLanguage

    class BrokenLinkLanguage(ToyLanguage):
        def link(self, project):
            raise RuntimeError("cannot link")

    source_root = tmp_path / "src"
    source_root.mkdir()
    (source_root / "dog.toy").write_text(TOY_SOURCE, encoding="utf-8")
    output_base = tmp_path / "out"

    summary = run(BrokenLinkLanguage(), [source_root], output_base)

    assert summary.link_error == "RuntimeError: cannot link"
    assert summary.has_errors
    assert summary.generated == 1
    assert "zoo.Dog -->" not in (output_base / FULL_DIAGRAM_DIR / "dog.puml").read_text(encoding="utf-8")


def test_core_knows_only_uml_kinds():
    from docgen.core.model import TypeKind

    assert {kind.name for kind in TypeKind} == UML_KINDS


def test_core_has_no_relation_inference():
    import docgen.core.language as language
    import docgen.core.model as model
    import docgen.core.relations as relations

    leftovers = [
        name for module, name in (
            (model, "FieldUsage"), (relations, "RelationPolicy"), (relations, "FieldFacts"),
            (relations, "usage_relations"), (language.Language, "relation_policy"),
            (language.Language, "vocabulary"), (language.Language, "class_stereotype"),
        )
        if hasattr(module, name)
    ]
    assert leftovers == []


def test_core_depends_on_no_toolkit_or_language():
    toolkit_imports = [
        module for module in _core_imports()
        if module.startswith(("docgen.oo", "docgen.clike", "docgen.languages"))
    ]

    assert toolkit_imports == []


def test_object_oriented_languages_use_the_shared_toolkit():
    from docgen.languages import REGISTRY
    from docgen.oo.language import ObjectOrientedLanguage

    offenders = [name for name, language in REGISTRY.items() if not isinstance(language, ObjectOrientedLanguage)]

    assert offenders == []


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


def test_readme_documents_every_registered_language():
    from docgen.languages import REGISTRY

    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")

    missing = [name for name in REGISTRY if f"generate_class_diagramm_{name}.py" not in readme and name != "csharp"]
    assert missing == []
    assert "generate_class_diagramm.py" in readme  # the C# script keeps its historical name
