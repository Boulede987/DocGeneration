"""Rust support, observed through the entry script on tests/fixtures/rust
(requirements: .claude/workflow/add-rust-support/NEEDS.md; linking flow:
docs/Algorithms/rust_link.puml)."""

import re
import subprocess
from pathlib import Path

import pytest

from conftest import FIXTURES, run_script

RUST_SCRIPT = "generate_class_diagramm_rust.py"
RUST_SOURCE_ROOT = FIXTURES / "rust" / "src"
BASE_DIAGRAM_DIR = "ClassDiagram"
FULL_DIAGRAM_DIR = "ClassDiagram-Full"
VIEWS_DIR = "Modules-Full"
PROJECT_VIEW = "_project"
EXIT_FILE_ERRORS = 1
ROOT_FILE = "lib"
PRODUCT_FILE = "model/product"
TAG_FILE = "model/tag"
MONEY_FILE = "util/money"
PRICING_FILE = "util/pricing"
ORDERS_FILE = "service/orders"
BILLING_FILE = "service/billing"
GENERATED_FILES = (ROOT_FILE, PRODUCT_FILE, TAG_FILE, MONEY_FILE, PRICING_FILE, ORDERS_FILE, BILLING_FILE)
SUBMODULE_ONLY_FILES = ("model/mod", "util/mod", "service/mod")
IMPLS_ONLY_FILE = "service/extensions"
PRODUCT_VIEW = "product"
ARROW = re.compile(r" (\*-->|o-->|-->|\.\.>|--\|>|\.\.\|>)( \"0\.\.\*\")? ")


@pytest.fixture(scope="module")
def rust_run(tmp_path_factory: pytest.TempPathFactory) -> tuple[subprocess.CompletedProcess[str], Path]:
    """One generator run over the fixture crate, shared by every test here."""
    output_base = tmp_path_factory.mktemp("rust")
    result = run_script(RUST_SCRIPT, RUST_SOURCE_ROOT, "-o", output_base, cwd=output_base)
    return result, output_base


def _path(run, file_path: str, diagram_dir: str = FULL_DIAGRAM_DIR) -> Path:
    _result, output_base = run
    return output_base / diagram_dir / f"{file_path}.puml"


def _lines(run, file_path: str, diagram_dir: str = FULL_DIAGRAM_DIR) -> list[str]:
    return [line.strip() for line in _path(run, file_path, diagram_dir).read_text(encoding="utf-8").splitlines()]


def _relations(run, file_path: str, diagram_dir: str = FULL_DIAGRAM_DIR) -> list[str]:
    return [line for line in _lines(run, file_path, diagram_dir) if ARROW.search(line)]


def _block(lines: list[str], header: str) -> list[str]:
    """The lines between 'header {' and its closing brace."""
    opening = f"{header} {{"
    assert opening in lines, f"{opening!r} not drawn"
    start = lines.index(opening)
    depth, end = 0, start
    for end in range(start, len(lines)):
        depth += lines[end].endswith("{") - (lines[end] == "}")
        if depth == 0:
            break
    return lines[start + 1:end]


def _members(run, file_path: str, header: str) -> list[str]:
    return _block(_lines(run, file_path), header)


# --- running ---------------------------------------------------------------

def test_unparsable_file_is_reported_and_exit_code_signals_it(rust_run):
    result, _output_base = rust_run

    assert result.returncode == EXIT_FILE_ERRORS
    assert any("ERROR" in line and "broken.rs" in line for line in result.stdout.splitlines())


def test_every_other_file_with_declarations_is_generated(rust_run):
    missing = [file_path for file_path in GENERATED_FILES if not _path(rust_run, file_path).is_file()]

    assert missing == []
    assert _path(rust_run, PROJECT_VIEW, VIEWS_DIR).is_file()


# --- modules ---------------------------------------------------------------

def test_types_are_drawn_inside_their_file_module(rust_run):
    module = _block(_lines(rust_run, PRODUCT_FILE), "namespace model.product")

    assert "class Product {" in module


def test_crate_root_items_have_no_module(rust_run):
    lines = _lines(rust_run, ROOT_FILE)

    assert "class crate <<module>> {" in lines
    assert not any(line.startswith("namespace ") for line in lines)


def test_inline_module_types_are_drawn_in_the_file_module(rust_run):
    assert _members(rust_run, ORDERS_FILE, "class Draft") == ["+ id : u32", "- source : Option<Box<dyn Repository>>"]


def test_use_inside_an_inline_module_resolves_from_that_module(rust_run):
    assert "service.orders.Draft *--> service.orders.Repository" in _relations(rust_run, ORDERS_FILE)


def test_imports_of_test_modules_do_not_affect_the_file(rust_run):
    result, _output_base = rust_run

    assert "+ tag_count() : usize" in _members(rust_run, PRODUCT_FILE, "class Product")
    assert not any("impl Product" in line for line in result.stdout.splitlines())


def test_test_modules_are_skipped_even_with_a_comment_or_combined_cfg(rust_run):
    lines = _lines(rust_run, ORDERS_FILE)

    assert "class OrderService {" in lines
    assert not any("TestOnly" in line or "SlowOnly" in line for line in lines)


def test_files_only_declaring_submodules_get_no_diagram(rust_run):
    assert _path(rust_run, PRODUCT_FILE).is_file()
    assert [file_path for file_path in SUBMODULE_ONLY_FILES if _path(rust_run, file_path).exists()] == []


# --- declarations ----------------------------------------------------------

def test_pub_field_is_public(rust_run):
    assert "+ name : String" in _members(rust_run, PRODUCT_FILE, "class Product")


def test_field_without_visibility_is_private(rust_run):
    assert "- price : Money" in _members(rust_run, PRODUCT_FILE, "class Product")


def test_restricted_pub_fields_are_package_visible(rust_run):
    product = _members(rust_run, PRODUCT_FILE, "class Product")

    assert "~ attributes : HashMap<String, String>" in product
    assert "~ code : u32" in product


def test_pub_self_is_private(rust_run):
    assert "- secret : u8" in _members(rust_run, PRODUCT_FILE, "class Category")


def test_collection_field_is_shown_as_many(rust_run):
    assert "- tags : Tag[*]" in _members(rust_run, PRODUCT_FILE, "class Product")


def test_tuple_struct_fields_are_numbered_ignoring_attributes(rust_run):
    assert _members(rust_run, PRODUCT_FILE, "class Sku") == ["+ 0 : u32", "- 1 : String"]


def test_lifetimes_are_not_shown(rust_run):
    assert _members(rust_run, PRODUCT_FILE, "class View") == ["+ product : &Product"]


def test_type_parameters_are_shown(rust_run):
    assert "+ inner : T" in _members(rust_run, PRODUCT_FILE, "class Wrapper<T>")


def test_enum_lists_its_variants(rust_run):
    assert _members(rust_run, PRODUCT_FILE, "enum Status <<enum>>") == ["Draft", "Published", "Archived", "Tagged"]


def test_trait_is_an_interface_with_its_methods(rust_run):
    priced = _members(rust_run, PRODUCT_FILE, "interface Priced <<interface>>")

    assert "+ price() : Money" in priced
    assert "+ currency() : Currency" in priced


# --- impl blocks -------------------------------------------------------------

def test_inherent_impl_methods_join_their_type(rust_run):
    product = _members(rust_run, PRODUCT_FILE, "class Product")

    assert "+ {static} new(&str, Money) : Self" in product
    assert "+ tag_count() : usize" in product
    assert "- rename(String)" in product


def test_associated_const_is_a_static_member(rust_run):
    assert "+ {static} MAX_TAGS : usize" in _members(rust_run, PRODUCT_FILE, "class Product")


def test_generic_impl_methods_join_their_generic_type(rust_run):
    assert "+ get() : &T" in _members(rust_run, PRODUCT_FILE, "class Wrapper<T>")


def test_impl_in_another_file_joins_the_type_in_its_own_diagram(rust_run):
    assert "+ discounted(u32) : Money" in _members(rust_run, PRODUCT_FILE, "class Product")


def test_file_with_only_impls_gets_no_diagram(rust_run):
    assert _path(rust_run, PRODUCT_FILE).is_file()
    assert not _path(rust_run, IMPLS_ONLY_FILE).exists()


def test_impl_of_a_type_outside_the_crate_is_a_note(rust_run):
    result, _output_base = rust_run

    assert any(
        "NOTE" in line and "extensions.rs" in line and "impl u32: type not in the crate" in line
        for line in result.stdout.splitlines()
    )


# --- relations ---------------------------------------------------------------

def test_trait_impl_is_a_realization(rust_run):
    relations = _relations(rust_run, PRODUCT_FILE)

    assert "model.product.Product ..|> model.product.Describe" in relations
    assert "model.product.Product ..|> model.product.Priced" in relations


def test_supertrait_is_inheritance(rust_run):
    assert "model.product.Priced --|> model.product.Describe" in _relations(rust_run, PRODUCT_FILE)


def test_owned_field_is_composition(rust_run):
    assert "model.product.Product *--> util.money.Money" in _relations(rust_run, PRODUCT_FILE)


def test_owned_collection_is_composition_with_multiplicity(rust_run):
    assert 'model.product.Product *--> "0..*" model.tag.Tag' in _relations(rust_run, PRODUCT_FILE)


def test_boxed_field_inside_option_is_composition(rust_run):
    assert "model.product.Product *--> model.product.Category" in _relations(rust_run, PRODUCT_FILE)


def test_reference_counted_field_is_association(rust_run):
    assert "model.product.Product --> model.product.Marker" in _relations(rust_run, PRODUCT_FILE)


def test_weak_field_to_its_own_type_is_a_self_association(rust_run):
    assert "model.product.Category --> model.product.Category" in _relations(rust_run, PRODUCT_FILE)


def test_reference_field_is_association(rust_run):
    assert "model.product.View --> model.product.Product" in _relations(rust_run, PRODUCT_FILE)


def test_enum_variant_data_is_composition(rust_run):
    assert "model.product.Status *--> model.tag.Tag" in _relations(rust_run, PRODUCT_FILE)


def test_function_pointer_and_closure_fields_hold_nothing(rust_run):
    lines = _lines(rust_run, PRODUCT_FILE)

    assert "class Hooks {" in lines
    assert [line for line in _relations(rust_run, PRODUCT_FILE) if line.startswith("model.product.Hooks ")] == []


def test_boxed_trait_object_field_is_composition(rust_run):
    assert "service.orders.OrderService *--> service.orders.Repository" in _relations(rust_run, ORDERS_FILE)


def test_nested_use_group_resolves_its_names(rust_run):
    assert 'service.orders.OrderService *--> "0..*" model.tag.Tag' in _relations(rust_run, ORDERS_FILE)


def test_self_import_through_an_inline_module_resolves(rust_run):
    assert "service.orders.OrderService *--> service.orders.Draft" in _relations(rust_run, ORDERS_FILE)


def test_module_bound_by_use_self_resolves_paths_through_it(rust_run):
    assert "service.orders.OrderService *--> util.money.Currency" in _relations(rust_run, ORDERS_FILE)


def test_fully_qualified_type_without_import_resolves(rust_run):
    assert "service.orders.OrderService ..> model.product.Category" in _relations(rust_run, ORDERS_FILE)


def test_glob_import_resolves_signature_type(rust_run):
    assert "service.orders.OrderService ..> util.money.Money" in _relations(rust_run, ORDERS_FILE)


def test_renamed_import_resolves_to_the_original_trait(rust_run):
    assert "service.orders.OrderService ..> model.product.Priced" in _relations(rust_run, ORDERS_FILE)


def test_dependencies_are_in_full_views_only(rust_run):
    base = _relations(rust_run, ORDERS_FILE, BASE_DIAGRAM_DIR)

    assert "service.orders.OrderService *--> service.orders.Repository" in base
    assert "service.orders.OrderService ..> util.money.Money" not in base


def test_standard_library_types_draw_nothing(rust_run):
    relations = _relations(rust_run, PRODUCT_FILE)
    std_names = ("String", "HashMap", "Vec", "Option", "Box", "Rc", "Weak", "Self", "u32", "usize", "str")

    assert relations
    assert [line for line in relations if line.split()[-1].split(".")[-1] in std_names] == []


# --- free items and module dependencies --------------------------------------

def test_free_functions_constants_and_statics_make_a_module_box(rust_run):
    pricing = _members(rust_run, PRICING_FILE, "class pricing <<module>>")

    assert "+ {static} DEFAULT_RATE : u32" in pricing
    assert "- {static} COUNTER : u32" in pricing
    assert "+ {static} total(&[Product]) : Money" in pricing
    assert "- {static} round(i64) : i64" in pricing


def test_module_box_uses_become_dependencies(rust_run):
    relations = _relations(rust_run, PRICING_FILE)

    assert "util.pricing.pricing ..> util.money.Money" in relations
    assert "util.pricing.pricing ..> model.product.Product" in relations


def test_use_of_another_module_function_depends_on_its_box(rust_run):
    assert "service.orders.OrderService ..> util.pricing.pricing" in _relations(rust_run, ORDERS_FILE)


def test_glob_imported_function_depends_on_its_box(rust_run):
    assert "service.orders.OrderService ..> util.money.money" in _relations(rust_run, ORDERS_FILE)


def test_turbofish_type_argument_is_a_dependency(rust_run):
    assert "crate ..> model.tag.Tag" in _relations(rust_run, ROOT_FILE)


def test_root_module_constant_use_is_not_a_self_dependency(rust_run):
    lines = _lines(rust_run, ROOT_FILE)

    assert "class crate <<module>> {" in lines
    assert not any(line.startswith("crate ..> crate") for line in lines)


def test_parameter_named_like_an_imported_function_is_not_a_use(rust_run):
    lines = _lines(rust_run, BILLING_FILE)

    assert "class Billing {" in lines
    assert _relations(rust_run, BILLING_FILE) == []


# --- views -------------------------------------------------------------------

def test_module_views_group_types_by_module(rust_run):
    view = _lines(rust_run, PRODUCT_VIEW, VIEWS_DIR)

    assert "class Product {" in _block(view, "namespace model.product")
