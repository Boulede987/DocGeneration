# Adding a language

A language is a parser that turns one source file into the neutral model in
`docgen/core/model.py`. Everything after parsing is shared and needs no
change: rendering, relation classification, name resolution, per-file
diagrams, package views, and the command line.

## Checklist

1. **Create `docgen/languages/<lang>/`** with a `language.py` defining a
   subclass of `docgen.core.language.Language`:

   | Class attribute | Example (Java) |
   |---|---|
   | `name` | `"java"` — the registry key |
   | `source_suffix` | `".java"` |
   | `views_dir` | `"Packages"` — folder for package-level views |
   | `skinparam_lines` | `skinparam_lines([StereotypeStyle("record", ...)])` from `docgen.core.style` |
   | `vocabulary` | `TypeVocabulary(primitives=..., collection_wrappers=...)`; set `type_argument_brackets=("[", "]")` if the language writes `list[Foo]` |
   | `hidden_bases` (optional) | base classes never drawn, e.g. Unity's `MonoBehaviour` |

   and implementing `parse_file(source: SourceText) -> ParsedFile`.
   `SourceText` gives the file's text, its path relative to the source
   root it was found under, and its stem.

2. **Export it** from `docgen/languages/<lang>/__init__.py`.

3. **Register it**: add one instance to the tuple in
   `docgen/languages/__init__.py` (`REGISTRY`).

4. **Add an entry script** at the repo root, `generate_class_diagramm_<lang>.py`:

   ```python
   import sys

   from docgen.core.cli import main
   from docgen.languages import REGISTRY

   sys.exit(main(REGISTRY["<lang>"]))
   ```

5. **Add tests**: a fixture project under `tests/fixtures/<lang>/`, its
   reviewed output under `tests/golden/<lang>/`, and a golden test in
   `tests/test_golden_output.py`.

No file under `docgen/core/` changes.

## What `parse_file` must produce

A `ParsedFile` with:

- `package` — the file's grouping unit (package, namespace, module path), or
  `None`. It becomes the PlantUML namespace, so its segments must be
  separated by `.`. It may come from the text (Java `package`, C#
  `namespace`) or from `source.relative_path` (Python folders).
- `decls` — one `TypeDecl` per declared type (empty when the file declares
  none; the file is then skipped). Per kind:
  - all kinds: `name` (may include type parameters, e.g. `Box<T>`), `kind`,
    `modifiers` (words like `abstract`, `static`), `base_class`,
    `additional_bases` (further superclasses, for multiple inheritance),
    `interfaces` — type texts as written; a base must be a simple name
    (strip a module prefix or type arguments yourself).
  - `ENUM`: `enum_values`.
  - `INTERFACE`: `members`.
  - `MODULE`: a source module's free functions (static methods) and
    constants (static fields), with `signature_types`/`body_types` so the
    classes they use become dependencies. Drawn as `<<module>>`; add
    `style.MODULE_STYLE` to your `kind_styles` to color it.
  - class-like kinds (`CLASS`, `RECORD`, `STRUCT`): `members` in display
    order, plus the usage lists relations are computed from:
    `field_usages` (types held by fields/properties), `signature_types`
    (method return and parameter types), `body_types` (types used inside
    method bodies), `newed_types` (types instantiated).
- `hints` — where the file's names come from:
  `type_imports` for imports naming one type (`import a.b.Foo` →
  `{"Foo": "a.b"}`), `namespace_imports` for whole-package imports
  (C# `using a.b;`).

`Member.type` is display text: format collection types with
`vocabulary.uml_type()` where the language wants `Foo[*]` instead of
`List<Foo>`; use `None` for a method shown without a return type, or a
field whose type is unknown.

Raise when a file can't be parsed (e.g. a syntax error): the pipeline
reports that file, generates every other one, and exits with code 1.

## Optional hooks

Override on your `Language` subclass when the defaults don't fit:

- `enclosing_packages(package)` — packages visible without an import,
  closest first. Default: the file's own package only. C# returns every
  parent namespace and the global one.
- `class_stereotype(decl)` — default: `<<record>>` / `<<struct>>` by kind,
  then `<<abstract>>`, then `<<static>>`.
- `relation_policy(parsed_files)` — how a held type becomes a relation.
  Default: composition (`*-->`) when instantiated or public, association
  (`-->`) otherwise. Return a `RelationPolicy` subclass to change it; it
  receives every parsed file, so it can depend on the whole project (Unity
  finds ScriptableObject subclasses this way).

## Helpers for brace languages

`docgen/clike/` holds scanning helpers shared by Java and C#: comment
stripping, brace matching, depth-aware splitting, flattening a type body
into member statements, and scanning method bodies for used types. Use them
for any C-like language; a language with other syntax doesn't need them.

`tests/toy_language.py` is a complete minimal language in about 50 lines;
`docgen/languages/python/` is a full one built on Python's `ast` module
instead of the brace-language helpers.
