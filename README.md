# DocGeneration

Generates PlantUML class diagrams from source code: one diagram per source
file, plus "general" views per package/namespace/module, an overview linking
them, and a whole-project diagram. Each comes in a **base** variant
(inheritance + composition) and a **full** variant (every relation).

Requires Python 3.10+. Only Rust needs third-party packages (tree-sitter):
`python -m pip install -r requirements.txt`. Render the `.puml` files with PlantUML (`export-svg.ps1` downloads
`plantuml.jar` and exports every diagram to SVG and PNG).

## Supported languages

| Language | Script | Views folder |
|---|---|---|
| Java | `generate_class_diagramm_java.py` | `Packages/` |
| C# | `generate_class_diagramm.py` | `Namespaces/` |
| Unity (C#) | `generate_class_diagramm_unity.py` | `Namespaces/` |
| Python | `generate_class_diagramm_python.py` | `Packages/` |
| Rust | `generate_class_diagramm_rust.py` | `Modules/` |

Every script takes the same options:

```
python <script> SRC_DIR [SRC_DIR ...] [-o OUT] [--exclude GLOB ...]
```

- `SRC_DIR`: one or more source roots. Pass every module's root in one run
  so cross-module relations and the views are complete.
- `-o OUT`: output root (default: `<first SRC_DIR>/Modelisation`).
- `--exclude GLOB`: skip files whose path relative to their root matches
  (repeatable, case-sensitive; `*` also crosses folders, so `tests/*` skips
  everything under `tests`; `\` and a leading `./` are accepted).
- The C# and Unity scripts also accept the historical form
  `SRC_DIR OUT_DIR` (when `OUT_DIR` contains no source file).

Output, under `OUT`:

| Folder | Contents |
|---|---|
| `ClassDiagram/`, `ClassDiagram-Full/` | one diagram per source file |
| `Fragments/`, `Fragments-Full/` | the same without `@startuml`/styling, for `!include` |
| `<Views>/`, `<Views>-Full/` | one diagram per package, `_overview.puml`, `_project.puml` |

A file that can't be parsed is reported and skipped; every other file is
still generated, and the script exits with code 1.

### Java

- Classes, interfaces, enums, records (components as public fields), with
  fields and methods.
- Relations: `extends`/`implements`; composition when a field type is
  instantiated in the class or the field is public, association otherwise;
  dependency for types only in signatures or method bodies.
- Packages come from `package` declarations; single-type imports place
  referenced classes in their package.

Caveats:
- Parsing is regex-based: unusual syntax can be missed.
- Methods without any modifier (package-private) are not shown.
- Interface methods always show their return type, `: void` included.
- Nested types are drawn at package level, not inside their outer class.
- Imports assume lowercase package names (the first capitalized segment
  starts the class path).

### C#

- Classes, structs, interfaces, enums, with fields, properties and methods;
  same relation rules as Java (properties count as fields).
- Namespaces from `namespace` declarations (block or file-scoped); `using`
  directives and parent namespaces resolve referenced classes.

Caveats:
- Only a file's first namespace is read.
- In a base list, a name like `IFoo` is taken as an interface, the first
  other name as the base class.
- Interface properties are not shown.
- Partial classes are drawn once per file.

### Unity (C#)

Everything from C#, plus Unity conventions:
- Engine base classes (`MonoBehaviour`, `ScriptableObject`, `GameObject`,
  `Component`) are not drawn.
- Direct `ScriptableObject` subclasses get `<<scriptableObject>>`; a field of
  a ScriptableObject type is drawn as aggregation (`o-->`), a shared asset.
- `[SerializeField]` fields count as composition, like public ones.

### Python

Pass the folder that **contains** your top-level packages (e.g. `src/`): a
module's package is its folder path relative to that root
(`shop/model/product.py` → `shop.model`).

- Classes with fields from class-level annotations and `self.x` assignments
  in `__init__` (typed by annotation, by the class constructed, or by the
  annotated `__init__` parameter assigned); methods, `@property`,
  `@staticmethod`/`@classmethod` (static), `@abstractmethod`.
- Visibility from naming: `__x` private, `_x` protected, otherwise public.
- Enum subclasses → enums; `Protocol` → interfaces; `ABC` base or
  `@abstractmethod` → abstract; `@dataclass` → `<<dataclass>>`; multiple
  inheritance drawn.
- Free functions and module variables (constants and module state such as
  caches) appear in a `<<module>>` box named after the module; the classes
  they use become dependencies. Only top-level statements count: names bound
  under `if`/`try` (e.g. `if TYPE_CHECKING:`) are left out.
- Absolute, relative and module imports resolve referenced classes to
  their package.
- Using another project module's function or constant (`from .x import f`
  then `f()`, `from . import x` then `x.f()`, `import a.x [as y]` then
  `a.x.f()` / `y.f()`) draws a dependency from the class or module box
  whose code uses it to that module's box (full views only).

Caveats:
- No type inference beyond annotations, constructor calls and annotated
  `__init__` parameters: an unannotated value has no type and no relation.
- Calls to methods of objects (`self.repository.find()`) are not drawn
  without a typed attribute: only imported module names and classes are
  recognized. Uses of the standard library and third-party modules draw
  nothing.
- Scopes are not told apart: a parameter or local variable named like an
  imported function (`def go(helper): helper()`) still counts as a use of
  that function.
- Typed public attributes (no underscore) count as composition, like public
  fields in Java/C#.
- Capitalization is the only evidence that a callee is a class: a
  capitalized factory function reads as a constructor.

### Rust

```
python -m pip install -r requirements.txt
python generate_class_diagramm_rust.py path/to/crate/src -o docs/Modelisation
```

Pass the crate's `src/` folder: `lib.rs` (or `main.rs`) there is the crate
root, `a/b.rs` and `a/b/mod.rs` are module `a.b`. Parsed with tree-sitter.

- `struct` (named, tuple, unit) → class with its fields (tuple fields named
  `0`, `1`...); `enum` → enum with its variants; `trait` → interface with
  its methods; type parameters shown, lifetimes left out.
- `impl` blocks add their methods to the type, even from another file;
  methods without a `self` receiver are static. `impl Trait for Type` →
  `..|>`; supertraits (`trait A: B`) → `--|>`.
- Visibility: `pub` public, `pub(crate)`/`pub(super)`/`pub(in ...)`
  package (`~`), none private.
- Relations follow ownership: a field holding a type by value, in a `Box`
  or a collection → composition (`"0..*"` for collections); through `&`,
  `Rc`, `Arc` or `Weak` → association. Types in signatures and bodies →
  dependencies.
- Free functions, constants and statics appear in a `<<module>>` box
  (named after the module, `crate` for the root, drawn inside its module);
  using another module's function or constant (`use` or a path such as
  `crate::util::f()`) draws a dependency to that module's box.
- Names resolve with Rust's rules: `crate::`, `self::`, `super::`, `use`
  (grouped, renamed with `as`, glob `*`), then the file's own module.

Caveats:
- Macros are not expanded: types or impls generated by macros are not seen.
- Types in an inline `mod x { }` are drawn in the file's module;
  `#[cfg(test)]` modules are skipped.
- An `impl` of a type outside the crate (`impl MyTrait for u32`) is
  reported as a NOTE and not drawn.
- One crate per run: several crates with the same module names would merge
  (each `src/bin/*.rs` is its own crate: run it separately).
- Trait associated types and consts are not drawn; types declared twice
  under different `#[cfg]` conditions are drawn once.
- Scopes are told apart only for parameters and `let`/`match` patterns: a
  local named like an imported function declared any other way still
  counts as a use of it.
- A file tree-sitter can't parse without repairs is reported as an error.

## Tests

```
python -m pip install pytest
python -m pytest
```

`tests/golden/` holds reviewed reference output per language: generated
diagrams must stay byte-identical unless a change is intended.

## This project's own diagrams

`docs/Modelisation/` is generated from this repository by its own Python
generator, and a test checks it matches the code. After changing the code,
regenerate it:

```
python generate_class_diagramm_python.py . --exclude "tests/*" -o docs/Modelisation
```

## Adding a language

See `docs/ADDING_A_LANGUAGE.md`.

## Database diagrams

`generate_mcd.py` and `generate_mld.py` produce Merise conceptual and
logical data models from an SQL schema (`DBSetUp.sql`).
