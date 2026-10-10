"""Python parsing edge cases, through the Language contract
(PythonLanguage.parse_file) on small inline sources."""

from pathlib import Path
from textwrap import dedent

from docgen.core.model import Member, ParsedFile, SourceText, TypeDecl, Visibility
from docgen.languages.python import PythonLanguage

MODULE_IN_PACKAGE = Path("pkg") / "module.py"
ROOT_MODULE = Path("module.py")
PACKAGE_INIT = Path("pkg") / "__init__.py"
ROOT_INIT = Path("__init__.py")
MODULE_BOX = MODULE_IN_PACKAGE.stem  # a module box is named after its file


def _parse(source: str, relative_path: Path = MODULE_IN_PACKAGE) -> ParsedFile:
    return PythonLanguage().parse_file(SourceText(relative_path, dedent(source)))


def _declaration(parsed: ParsedFile, name: str) -> TypeDecl:
    return next(declaration for declaration in parsed.declarations if declaration.name == name)


def _member(declaration: TypeDecl, name: str) -> Member:
    return next(member for member in declaration.members if member.name == name)


def _declaration_names(parsed: ParsedFile) -> list[str]:
    return [declaration.name for declaration in parsed.declarations]


def _member_names(declaration: TypeDecl) -> list[str]:
    return [member.name for member in declaration.members]


def test_enum_annotation_without_value_is_not_a_member():
    parsed = _parse("""
        from enum import Enum
        class Color(Enum):
            RED = 1
            note: str
    """)

    assert _declaration(parsed, "Color").enum_values == ["RED"]


def test_relative_import_above_the_top_level_package_is_ignored():
    parsed = _parse("from ...elsewhere import Target\n")

    assert parsed.hints.namespace_imports == set()


def test_relative_import_in_a_root_module_is_ignored():
    parsed = _parse("from .sibling import Target\n", relative_path=ROOT_MODULE)

    assert parsed.hints.namespace_imports == set()


def test_literal_arguments_keep_their_quotes():
    parsed = _parse("""
        from typing import Literal
        class Shape:
            kind: Literal["circle", "square"]
    """)

    assert _member(_declaration(parsed, "Shape"), "kind").type == "Literal['circle', 'square']"


def test_annotated_metadata_keeps_its_quotes():
    parsed = _parse("""
        from typing import Annotated
        class Shape:
            size: Annotated[int, "in pixels"]
    """)

    assert _member(_declaration(parsed, "Shape"), "size").type == "Annotated[int, 'in pixels']"


def test_quoted_type_expression_is_read_as_a_type():
    parsed = _parse("""
        class Node:
            children: "list[Node]"
            parent: "Node | None"
    """)
    node = _declaration(parsed, "Node")

    assert _member(node, "children").type == "Node[*]"
    assert _member(node, "parent").type == "Node | None"


def test_single_underscore_name_ending_in_double_underscore_is_protected():
    parsed = _parse("""
        class Widget:
            def _hook__(self): ...
            def __repr__(self): ...
    """)
    widget = _declaration(parsed, "Widget")

    assert _member(widget, "_hook__").visibility is Visibility.PROTECTED
    assert _member(widget, "__repr__").visibility is Visibility.PUBLIC


def test_module_qualified_classvar_is_static():
    parsed = _parse("""
        import typing
        class Settings:
            defaults: typing.ClassVar[dict] = {}
    """)

    assert _member(_declaration(parsed, "Settings"), "defaults").is_static


def test_attribute_set_in_a_function_nested_in_init_is_ignored():
    parsed = _parse("""
        class Worker:
            def __init__(self):
                self.ready = True
                def later():
                    self.result = 1
    """)

    assert _member_names(_declaration(parsed, "Worker")) == ["ready"]


def test_chained_and_tuple_assignments_create_every_attribute():
    parsed = _parse("""
        class Point:
            def __init__(self, x: int, y: int):
                self.x = self.left = x
                self.y, self.top = y, y
    """)

    assert _member_names(_declaration(parsed, "Point")) == ["x", "left", "y", "top"]


def test_getter_decorator_does_not_list_the_property_twice():
    parsed = _parse("""
        class Box:
            @property
            def size(self) -> int: ...
            @size.getter
            def size(self) -> int: ...
    """)

    assert _member_names(_declaration(parsed, "Box")) == ["size"]


def test_cached_property_is_a_property():
    parsed = _parse("""
        from functools import cached_property
        class Report:
            @cached_property
            def total(self) -> int: ...
    """)

    assert _member(_declaration(parsed, "Report"), "total").params == []
    assert _member(_declaration(parsed, "Report"), "total").kind.name == "PROPERTY"


def test_variadic_parameters_appear_in_the_signature():
    parsed = _parse("""
        class Logger:
            def log(self, level: int, *messages: str, **context): ...
    """)

    assert _member(_declaration(parsed, "Logger"), "log").params == ["int", "*str", "**context"]


def test_package_init_module_box_is_named_after_its_folder():
    parsed = _parse("def setup() -> None: ...\n", relative_path=PACKAGE_INIT)

    assert _declaration_names(parsed) == [PACKAGE_INIT.parent.name]


def test_root_init_module_box_keeps_its_file_name():
    parsed = _parse("def setup() -> None: ...\n", relative_path=ROOT_INIT)

    assert _declaration_names(parsed) == [ROOT_INIT.stem]


def test_dunder_module_names_are_not_module_variables():
    parsed = _parse("""
        __all__ = ["LIMIT"]
        __version__ = "1.0"
        LIMIT = 3
    """)

    assert _member_names(_declaration(parsed, MODULE_BOX)) == ["LIMIT"]


def test_typing_helpers_are_not_module_variables():
    parsed = _parse("""
        from typing import NewType, TypeAlias, TypeVar
        T = TypeVar("T")
        UserId = NewType("UserId", int)
        Pair: TypeAlias = tuple[int, int]
        LIMIT = 3
    """)

    assert _member_names(_declaration(parsed, MODULE_BOX)) == ["LIMIT"]


def test_bare_module_annotation_is_not_a_module_variable():
    parsed = _parse("""
        pending: int
        LIMIT = 3
    """)

    assert _member_names(_declaration(parsed, MODULE_BOX)) == ["LIMIT"]


def test_module_state_is_a_module_variable():
    parsed = _parse("""
        _cache = {}
        counter = 0
    """)

    assert _member_names(_declaration(parsed, MODULE_BOX)) == ["_cache", "counter"]


def test_chained_and_tuple_module_assignments_create_every_variable():
    parsed = _parse("""
        A = B = 1
        C, D = 2, 3
    """)

    assert _member_names(_declaration(parsed, MODULE_BOX)) == ["A", "B", "C", "D"]


def test_conditional_module_bindings_are_ignored():
    parsed = _parse("""
        from typing import TYPE_CHECKING
        if TYPE_CHECKING:
            HIDDEN = 1
        LIMIT = 3
    """)

    assert _member_names(_declaration(parsed, MODULE_BOX)) == ["LIMIT"]


def test_annotated_module_variable_keeps_its_type():
    parsed = _parse("LIMIT: int = 3\n")

    assert _member(_declaration(parsed, MODULE_BOX), "LIMIT").type == "int"


def test_module_with_only_variables_gets_a_box():
    parsed = _parse("LIMIT = 3\n")

    assert _declaration_names(parsed) == [MODULE_BOX]


def test_async_module_function_is_a_static_method():
    parsed = _parse("async def fetch() -> int: ...\n")

    fetch = _member(_declaration(parsed, MODULE_BOX), "fetch")
    assert fetch.is_static and fetch.type == "int"


def test_module_box_comes_after_the_module_classes():
    parsed = _parse("""
        class Widget: ...
        def build() -> Widget: ...
    """)

    assert _declaration_names(parsed) == ["Widget", MODULE_BOX]


def test_module_box_named_like_a_class_of_its_module_gets_a_suffix():
    parsed = _parse("""
        class module: ...
        def build() -> module: ...
    """)

    assert _declaration_names(parsed) == [MODULE_BOX, f"{MODULE_BOX}_module"]
