"""Python support, observed through the entry script on tests/fixtures/python
(requirements: .claude/workflow/adding-python/NEEDS.md)."""

import subprocess
from pathlib import Path

import pytest

from conftest import FIXTURES, run_script

PYTHON_SCRIPT = "generate_class_diagramm_python.py"
PYTHON_FIXTURE = FIXTURES / "python"
BASE_DIAGRAM_DIR = "ClassDiagram"
FULL_DIAGRAM_DIR = "ClassDiagram-Full"
VIEWS_DIR = "Packages-Full"
EXIT_FILE_ERRORS = 1
PRODUCT_MODULE = "shop/model/product"
BASE_MODULE = "shop/model/base"
ORDERS_MODULE = "shop/service/orders"
HELPERS_MODULE = "shop/util/helpers"
ROOT_MODULE = "app"


@pytest.fixture(scope="module")
def python_run(tmp_path_factory: pytest.TempPathFactory) -> tuple[subprocess.CompletedProcess[str], Path]:
    """One generator run over the fixture, shared by every test here."""
    output_base = tmp_path_factory.mktemp("python")
    result = run_script(PYTHON_SCRIPT, PYTHON_FIXTURE, "-o", output_base, cwd=output_base)
    return result, output_base


def _full_diagram(python_run: tuple[subprocess.CompletedProcess[str], Path], module_path: str) -> str:
    _result, output_base = python_run
    return (output_base / FULL_DIAGRAM_DIR / f"{module_path}.puml").read_text(encoding="utf-8")


def test_syntax_error_is_reported_and_exit_code_signals_it(python_run):
    result, _output_base = python_run

    error_lines = [line for line in result.stdout.splitlines() if "ERROR" in line]
    assert result.returncode == EXIT_FILE_ERRORS
    assert len(error_lines) == 1
    assert "broken.py" in error_lines[0] and "SyntaxError" in error_lines[0]


def test_other_files_are_generated_despite_a_syntax_error(python_run):
    _result, output_base = python_run

    assert (output_base / BASE_DIAGRAM_DIR / "shop" / "model" / "product.puml").is_file()
    assert not (output_base / BASE_DIAGRAM_DIR / "shop" / "service" / "broken.puml").exists()


def test_classes_are_placed_in_their_folder_package(python_run):
    diagram = _full_diagram(python_run, PRODUCT_MODULE)

    assert "namespace shop.model {" in diagram
    assert "class Tag {" in diagram


def test_root_module_classes_have_no_package(python_run):
    diagram = _full_diagram(python_run, ROOT_MODULE)

    assert "namespace" not in diagram
    assert "class App {" in diagram


def test_dataclass_is_marked_with_a_stereotype(python_run):
    assert "class Product <<dataclass>> {" in _full_diagram(python_run, PRODUCT_MODULE)


def test_annotated_class_fields_show_their_type(python_run):
    diagram = _full_diagram(python_run, PRODUCT_MODULE)

    assert "  + name : str" in diagram
    assert "  + price : Money" in diagram


def test_collection_annotation_becomes_multiplicity(python_run):
    diagram = _full_diagram(python_run, PRODUCT_MODULE)

    assert "  + tags : Tag[*]" in diagram
    assert 'shop.model.Product *--> "0..*" shop.model.Tag' in diagram


def test_unannotated_class_attribute_is_static(python_run):
    assert "  + {static} MAX_LENGTH" in _full_diagram(python_run, PRODUCT_MODULE)


def test_enum_subclass_is_an_enum_with_its_values(python_run):
    diagram = _full_diagram(python_run, PRODUCT_MODULE)

    assert "enum Category <<enum>> {" in diagram
    assert "  BOOKS\n  GAMES\n  MUSIC\n}" in diagram


def test_abc_subclass_is_abstract_and_abc_is_not_drawn(python_run):
    diagram = _full_diagram(python_run, BASE_MODULE)

    assert "abstract class Entity <<abstract>> {" in diagram
    assert "--|> ABC" not in diagram


def test_underscore_prefixes_set_visibility(python_run):
    base = _full_diagram(python_run, BASE_MODULE)
    orders = _full_diagram(python_run, ORDERS_MODULE)

    assert "  # _version" in base
    assert "  - __orders : dict[str, Order]" in orders


def test_untyped_instance_attribute_has_no_type(python_run):
    assert "  + history\n" in _full_diagram(python_run, ORDERS_MODULE)


def test_constructor_call_gives_an_attribute_its_type(python_run):
    assert "  + gateway : PaymentGateway" in _full_diagram(python_run, ORDERS_MODULE)


def test_attribute_assigned_from_annotated_init_parameter_takes_its_type(python_run):
    base = _full_diagram(python_run, BASE_MODULE)
    orders = _full_diagram(python_run, ORDERS_MODULE)

    assert "  + id : int" in base
    assert "  + repository : Repository" in orders


def test_attribute_typed_from_init_parameter_gets_its_relation(python_run):
    assert "shop.service.Order *--> shop.model.Product" in _full_diagram(python_run, ORDERS_MODULE)


def test_init_is_not_shown(python_run):
    diagram = _full_diagram(python_run, ORDERS_MODULE)

    assert "class OrderService {" in diagram
    assert "__init__" not in diagram


def test_abstractmethod_is_abstract(python_run):
    assert "  + {abstract} validate()" in _full_diagram(python_run, BASE_MODULE)


def test_property_is_listed_with_its_type(python_run):
    assert "  + key : str" in _full_diagram(python_run, BASE_MODULE)


def test_static_and_class_methods_are_static_without_bound_parameter(python_run):
    orders = _full_diagram(python_run, ORDERS_MODULE)

    assert "  + {static} total(list[Product]) : Money" in orders
    assert "  + {static} create(Repository) : OrderService" in orders


def test_underscore_method_is_protected(python_run):
    assert "  # _check(Product) : bool" in _full_diagram(python_run, ORDERS_MODULE)


def test_protocol_is_an_interface(python_run):
    diagram = _full_diagram(python_run, ORDERS_MODULE)

    assert "interface Repository <<interface>> {" in diagram
    assert "  + find(str) : Optional[Product]" in diagram


def test_every_base_class_is_drawn(python_run):
    diagram = _full_diagram(python_run, ORDERS_MODULE)

    assert "shop.service.OrderService --|> shop.service.BaseService" in diagram
    assert "shop.service.OrderService --|> shop.service.Auditable" in diagram


def test_generic_base_is_not_drawn(python_run):
    diagram = _full_diagram(python_run, HELPERS_MODULE)

    assert "class Box {" in diagram
    assert "Generic" not in diagram


def test_absolute_import_places_used_class_in_its_package(python_run):
    assert "shop.service.OrderService ..> shop.model.Money" in _full_diagram(python_run, ORDERS_MODULE)


def test_relative_module_import_resolves_dotted_base(python_run):
    assert "shop.service.Order --|> shop.model.Entity" in _full_diagram(python_run, ORDERS_MODULE)


def test_relative_import_resolves_static_call_target(python_run):
    assert "shop.service.OrderService ..> shop.util.Validator" in _full_diagram(python_run, ORDERS_MODULE)


def test_package_views_group_classes_by_folder(python_run):
    _result, output_base = python_run

    project = (output_base / VIEWS_DIR / "_project.puml").read_text(encoding="utf-8")
    assert "namespace shop.model {" in project
    assert "namespace shop.service {" in project
    assert (output_base / VIEWS_DIR / "model.puml").is_file()
