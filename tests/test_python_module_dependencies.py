"""Uses of another module's free functions and constants become dependency
arrows to that module's <<module>> box (requirements:
.claude/workflow/adding-python/NEEDS.md, increment 3; flow:
docs/Algorithms/module_dependencies.puml). Each test writes its own small
project."""

from pathlib import Path

from docgen.core.pipeline import run
from docgen.languages import REGISTRY

BASE_DIAGRAM_DIR = "ClassDiagram"
FULL_DIAGRAM_DIR = "ClassDiagram-Full"
DEPENDS = "..>"
TOOLS_SOURCE = "LIMIT = 3\n\n\ndef helper():\n    return LIMIT\n"


def _generate(tmp_path: Path, files: dict[str, str]) -> Path:
    source_root = tmp_path / "src"
    for relative_path, text in files.items():
        path = source_root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    output_base = tmp_path / "out"
    summary = run(REGISTRY["python"], [source_root], output_base)
    assert not summary.has_errors, summary
    return output_base


def _diagram_lines(output_base: Path, module_path: str, diagram_dir: str = FULL_DIAGRAM_DIR) -> list[str]:
    diagram = (output_base / diagram_dir / f"{module_path}.puml").read_text(encoding="utf-8")
    return [line.strip() for line in diagram.splitlines()]


def _relations(output_base: Path, module_path: str, diagram_dir: str = FULL_DIAGRAM_DIR) -> set[str]:
    return {line for line in _diagram_lines(output_base, module_path, diagram_dir) if f" {DEPENDS} " in line}


def _declares(output_base: Path, module_path: str, box_header: str) -> bool:
    """Guards a 'no arrow' check: the diagram exists and draws the box."""
    return any(line.startswith(box_header) for line in _diagram_lines(output_base, module_path))


def test_imported_function_called_in_a_method_makes_the_class_depend_on_the_module(tmp_path: Path):
    output = _generate(tmp_path, {
        "pkg/tools.py": TOOLS_SOURCE,
        "pkg/client.py": "from .tools import helper\n\n\nclass Client:\n    def run(self):\n        return helper()\n",
    })

    assert "pkg.Client ..> pkg.tools" in _relations(output, "pkg/client")


def test_imported_constant_read_in_a_function_makes_the_module_depend_on_the_module(tmp_path: Path):
    output = _generate(tmp_path, {
        "pkg/tools.py": TOOLS_SOURCE,
        "pkg/client.py": "from pkg.tools import LIMIT\n\n\ndef twice():\n    return LIMIT * 2\n",
    })

    assert "pkg.client ..> pkg.tools" in _relations(output, "pkg/client")


def test_relatively_imported_module_used_through_its_name(tmp_path: Path):
    output = _generate(tmp_path, {
        "pkg/tools.py": TOOLS_SOURCE,
        "pkg/client.py": "from . import tools\n\n\ndef go():\n    return tools.helper()\n",
    })

    assert "pkg.client ..> pkg.tools" in _relations(output, "pkg/client")


def test_absolutely_imported_module_used_through_its_name(tmp_path: Path):
    output = _generate(tmp_path, {
        "pkg/tools.py": TOOLS_SOURCE,
        "other/client.py": "from pkg import tools\n\n\nclass Client:\n    limit = tools.LIMIT\n",
    })

    assert "other.Client ..> pkg.tools" in _relations(output, "other/client")


def test_dotted_import_used_through_its_full_path(tmp_path: Path):
    output = _generate(tmp_path, {
        "pkg/tools.py": TOOLS_SOURCE,
        "other/client.py": "import pkg.tools\n\n\ndef go():\n    return pkg.tools.helper()\n",
    })

    assert "other.client ..> pkg.tools" in _relations(output, "other/client")


def test_aliased_import_used_through_its_alias(tmp_path: Path):
    output = _generate(tmp_path, {
        "pkg/tools.py": TOOLS_SOURCE,
        "other/client.py": "import pkg.tools as t\n\n\ndef go():\n    return t.helper()\n",
    })

    assert "other.client ..> pkg.tools" in _relations(output, "other/client")


def test_function_of_a_package_init_targets_the_package_box(tmp_path: Path):
    output = _generate(tmp_path, {
        "pkg/__init__.py": TOOLS_SOURCE,
        "other/client.py": "from pkg import helper\n\n\ndef go():\n    return helper()\n",
    })

    assert "other.client ..> pkg.pkg" in _relations(output, "other/client")


def test_renamed_module_box_is_the_target(tmp_path: Path):
    output = _generate(tmp_path, {
        "pkg/Widget.py": "class Widget:\n    pass\n\n\ndef make():\n    return Widget()\n",
        "pkg/client.py": "from .Widget import make\n\n\ndef go():\n    return make()\n",
    })

    assert "pkg.client ..> pkg.Widget_module" in _relations(output, "pkg/client")


def test_same_named_modules_resolve_to_the_imported_one(tmp_path: Path):
    output = _generate(tmp_path, {
        "first/tools.py": TOOLS_SOURCE,
        "second/tools.py": TOOLS_SOURCE,
        "second/client.py": "from first.tools import helper\n\n\ndef go():\n    return helper()\n",
    })

    assert _relations(output, "second/client") == {"second.client ..> first.tools"}


def test_several_uses_of_one_module_draw_one_arrow(tmp_path: Path):
    output = _generate(tmp_path, {
        "pkg/tools.py": TOOLS_SOURCE,
        "pkg/client.py": "from . import tools\n\n\ndef go():\n    return tools.helper() + tools.LIMIT\n",
    })

    lines = _diagram_lines(output, "pkg/client")

    assert lines.count("pkg.client ..> pkg.tools") == 1


def test_module_dependency_is_shown_in_full_views_only(tmp_path: Path):
    output = _generate(tmp_path, {
        "pkg/tools.py": TOOLS_SOURCE,
        "pkg/client.py": "from .tools import helper\n\n\ndef go():\n    return helper()\n",
    })

    assert "pkg.client ..> pkg.tools" in _relations(output, "pkg/client", FULL_DIAGRAM_DIR)
    assert "pkg.client ..> pkg.tools" not in _relations(output, "pkg/client", BASE_DIAGRAM_DIR)


def test_standard_library_module_draws_nothing(tmp_path: Path):
    output = _generate(tmp_path, {
        "pkg/client.py": "import re\nfrom os import path\n\n\ndef go():\n    return re.compile(path.sep)\n",
    })

    assert _declares(output, "pkg/client", "class client <<module>>")
    assert _relations(output, "pkg/client") == set()


def test_imported_class_does_not_point_at_its_module_box(tmp_path: Path):
    output = _generate(tmp_path, {
        "pkg/tools.py": TOOLS_SOURCE + "\n\nclass Thing:\n    pass\n",
        "pkg/client.py": "from .tools import Thing\n\n\ndef go():\n    return Thing()\n",
    })

    assert _relations(output, "pkg/client") == {"pkg.client ..> pkg.Thing"}


def test_attribute_the_module_does_not_define_draws_no_arrow(tmp_path: Path):
    output = _generate(tmp_path, {
        "pkg/tools.py": TOOLS_SOURCE,
        "pkg/client.py": "from . import tools\n\n\ndef go():\n    return tools.missing()\n",
    })

    assert _declares(output, "pkg/client", "class client <<module>>")
    assert _relations(output, "pkg/client") == set()


def test_module_using_its_own_functions_draws_nothing(tmp_path: Path):
    output = _generate(tmp_path, {
        "pkg/tools.py": TOOLS_SOURCE + "\n\ndef twice():\n    return helper() * 2\n",
    })

    assert _declares(output, "pkg/tools", "class tools <<module>>")
    assert _relations(output, "pkg/tools") == set()


def test_target_box_named_like_the_using_module_is_not_confused_with_it(tmp_path: Path):
    output = _generate(tmp_path, {
        "first/tools.py": TOOLS_SOURCE,
        "second/tools.py": "from first.tools import helper\n\n\ndef go():\n    return helper()\n",
    })

    assert _relations(output, "second/tools") == {"second.tools ..> first.tools"}


def test_import_without_use_draws_no_arrow(tmp_path: Path):
    output = _generate(tmp_path, {
        "pkg/tools.py": TOOLS_SOURCE,
        "pkg/client.py": "from .tools import helper\n\n\ndef go():\n    return 1\n",
    })

    assert _declares(output, "pkg/client", "class client <<module>>")
    assert _relations(output, "pkg/client") == set()


def test_assigning_to_an_imported_name_is_not_a_use(tmp_path: Path):
    output = _generate(tmp_path, {
        "pkg/tools.py": TOOLS_SOURCE,
        "pkg/client.py": "from .tools import helper\n\n\ndef go():\n    helper = 1\n    return 2\n",
    })

    assert _declares(output, "pkg/client", "class client <<module>>")
    assert _relations(output, "pkg/client") == set()


def test_star_import_draws_no_arrow(tmp_path: Path):
    output = _generate(tmp_path, {
        "pkg/tools.py": TOOLS_SOURCE,
        "pkg/client.py": "from .tools import *\n\n\ndef go():\n    return helper()\n",
    })

    assert _declares(output, "pkg/client", "class client <<module>>")
    assert _relations(output, "pkg/client") == set()


def test_aliased_imported_function_is_traced_to_its_module(tmp_path: Path):
    output = _generate(tmp_path, {
        "pkg/tools.py": TOOLS_SOURCE,
        "pkg/client.py": "from .tools import helper as assist\n\n\ndef go():\n    return assist()\n",
    })

    assert _relations(output, "pkg/client") == {"pkg.client ..> pkg.tools"}


def test_relative_import_two_levels_up(tmp_path: Path):
    output = _generate(tmp_path, {
        "pkg/tools.py": TOOLS_SOURCE,
        "pkg/sub/client.py": "from ..tools import helper\n\n\ndef go():\n    return helper()\n",
    })

    assert _relations(output, "pkg/sub/client") == {"pkg.sub.client ..> pkg.tools"}


def test_use_inside_a_nested_function_counts_for_the_enclosing_box(tmp_path: Path):
    output = _generate(tmp_path, {
        "pkg/tools.py": TOOLS_SOURCE,
        "pkg/client.py": "from .tools import helper\n\n\ndef outer():\n    def inner():\n        return helper()\n    return inner\n",
    })

    assert _relations(output, "pkg/client") == {"pkg.client ..> pkg.tools"}


def test_imported_constant_as_class_attribute_makes_the_class_depend_on_the_module(tmp_path: Path):
    output = _generate(tmp_path, {
        "pkg/tools.py": TOOLS_SOURCE,
        "pkg/client.py": "from .tools import LIMIT\n\n\nclass Client:\n    limit = LIMIT\n",
    })

    assert _relations(output, "pkg/client") == {"pkg.Client ..> pkg.tools"}


def test_import_inside_a_function_counts(tmp_path: Path):
    output = _generate(tmp_path, {
        "pkg/tools.py": TOOLS_SOURCE,
        "pkg/client.py": "def go():\n    from .tools import helper\n    return helper()\n",
    })

    assert _relations(output, "pkg/client") == {"pkg.client ..> pkg.tools"}


def test_later_import_of_a_name_wins_over_an_earlier_one(tmp_path: Path):
    output = _generate(tmp_path, {
        "first/tools.py": TOOLS_SOURCE,
        "second/tools.py": TOOLS_SOURCE,
        "pkg/client.py": (
            "def setup():\n    from first.tools import helper\n    return helper\n\n\n"
            "from second.tools import helper\n\n\ndef go():\n    return helper()\n"
        ),
    })

    assert _relations(output, "pkg/client") == {"pkg.client ..> second.tools"}
