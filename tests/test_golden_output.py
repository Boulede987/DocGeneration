"""Regression safety net: generated diagrams must stay byte-identical to the
golden output captured before the refactor (tests/golden, from f29ba37)."""

from pathlib import Path

import pytest

from conftest import FIXTURES, GOLDEN, assert_same_tree, run_script

JAVA_SCRIPT = "generate_class_diagramm_java.py"
CSHARP_SCRIPT = "generate_class_diagramm.py"
UNITY_SCRIPT = "generate_class_diagramm_unity.py"
OUT_OPTION = "-o"
JAVA_SOURCE_ROOT = FIXTURES / "java" / "src"
JAVA_LIBRARY_ROOT = FIXTURES / "java" / "lib"
DEFAULT_OUTPUT_DIR = "Modelisation"
BASE_DIAGRAM_DIR = "ClassDiagram"
FULL_DIAGRAM_DIR = "ClassDiagram-Full"
EXIT_USAGE_ERROR = 2


def test_java_two_roots_with_out_option_match_golden(tmp_path: Path):
    result = run_script(JAVA_SCRIPT, JAVA_SOURCE_ROOT, JAVA_LIBRARY_ROOT, OUT_OPTION, tmp_path, cwd=tmp_path)

    assert result.returncode == 0, result.stderr
    assert_same_tree(tmp_path, GOLDEN / "java")


@pytest.mark.parametrize("script, language", [(CSHARP_SCRIPT, "csharp"), (UNITY_SCRIPT, "unity")])
def test_legacy_src_out_form_output_matches_golden(tmp_path: Path, script: str, language: str):
    result = run_script(script, FIXTURES / language, tmp_path, cwd=tmp_path)

    assert result.returncode == 0, result.stderr
    assert_same_tree(tmp_path, GOLDEN / language)


@pytest.mark.parametrize("script, language", [(CSHARP_SCRIPT, "csharp"), (UNITY_SCRIPT, "unity")])
def test_unified_out_option_output_matches_golden(tmp_path: Path, script: str, language: str):
    result = run_script(script, FIXTURES / language, OUT_OPTION, tmp_path, cwd=tmp_path)

    assert result.returncode == 0, result.stderr
    assert_same_tree(tmp_path, GOLDEN / language)


def test_csharp_reference_across_two_roots_resolves_like_a_single_root(tmp_path: Path):
    model_root = FIXTURES / "csharp" / "Model"
    core_root = FIXTURES / "csharp" / "Core"
    diagram_name = "GameManager.puml"

    result = run_script(CSHARP_SCRIPT, model_root, core_root, OUT_OPTION, tmp_path, cwd=tmp_path)

    assert result.returncode == 0, result.stderr
    # Paths are relative to each root, so Core/ disappears from the path.
    actual = (tmp_path / FULL_DIAGRAM_DIR / diagram_name).read_bytes()
    expected = (GOLDEN / "csharp" / FULL_DIAGRAM_DIR / "Core" / diagram_name).read_bytes()
    assert actual == expected


def test_default_output_folder_is_modelisation_under_first_root(tmp_path: Path):
    source_root = tmp_path / "src"
    source_root.mkdir()
    (source_root / "Item.java").write_text("package shop;\npublic class Item { }\n", encoding="utf-8")

    result = run_script(JAVA_SCRIPT, source_root, cwd=tmp_path)

    assert result.returncode == 0, result.stderr
    assert (source_root / DEFAULT_OUTPUT_DIR / BASE_DIAGRAM_DIR / "Item.puml").is_file()


@pytest.mark.parametrize("script", [JAVA_SCRIPT, CSHARP_SCRIPT])
def test_missing_source_root_is_a_usage_error(tmp_path: Path, script: str):
    missing_root = tmp_path / "does-not-exist"

    result = run_script(script, missing_root, OUT_OPTION, tmp_path / "out", cwd=tmp_path)

    assert result.returncode == EXIT_USAGE_ERROR
    assert "source directory not found" in result.stderr
    assert not (tmp_path / "out").exists()
