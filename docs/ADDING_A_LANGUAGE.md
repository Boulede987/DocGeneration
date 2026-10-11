# Adding a language

The core (`docgen/core`) is a UML model plus the machinery around it:
discovery, the pipeline, name resolution, rendering, package views and the
command line. A language translates its source into that model: UML
classifiers with members, and the relations between them. **No file under
`docgen/core/` changes to add a language.**

Two routes:

- **Object-oriented route** (`docgen/oo`): for languages whose relations
  follow class-based rules — inheritance from bases, composition or
  association from fields, dependencies from signatures and method bodies.
  Java, C#, Unity and Python take it. You write a parser; the toolkit infers
  the relations.
- **Own route**: for languages with other rules (ownership, traits,
  impl blocks...). You implement the core contract directly and compute your
  own relations, reusing any toolkit piece that fits.
  `tests/toy_language.py` is a complete example in about 120 lines.

## Checklist (both routes)

1. **Create `docgen/languages/<lang>/`** with a `language.py` defining the
   language class (see the route below), and export it from its
   `__init__.py`.
2. **Register it**: add one instance to the tuple in
   `docgen/languages/__init__.py` (`REGISTRY`).
3. **Add an entry script** at the repo root, `generate_class_diagramm_<lang>.py`:

   ```python
   import sys

   from docgen.core.cli import main
   from docgen.languages import REGISTRY

   sys.exit(main(REGISTRY["<lang>"]))
   ```

4. **Add tests**: a fixture project under `tests/fixtures/<lang>/`, its
   reviewed output under `tests/golden/<lang>/`, a golden test in
   `tests/test_golden_output.py`, and behavior tests.
5. **Document it** in `README.md`: how to run it, what it maps, its caveats.

## The core contract

Subclass `docgen.core.language.Language[FactsT]`, where `FactsT` is whatever
your parser keeps to compute relations later.

| Class attribute | Example |
|---|---|
| `name` | `"java"` — the registry key |
| `source_suffix` | `".java"` |
| `views_dir` | `"Packages"` — folder for package-level views |
| `skinparam_lines` | `docgen.core.style.skinparam_lines([...])` |

Methods:

- `parse_file(source: SourceText) -> ParsedFile[FactsT]` — one file.
  `source` gives the text, the path relative to its source root, and the
  stem. Raise when the text can't be parsed: only that file fails, and the
  run exits with code 1.
- `link(project: Project[FactsT]) -> Mapping[ParsedFile, list[Relation]]` —
  once every file is parsed: each file's relations; a file left out has
  none. It may also complete declarations across files (methods declared
  away from their type) and add `notes` to files (non-fatal warnings,
  printed per file). If it raises, every diagram is still written, without
  relations, and the run exits with code 1.
- `enclosing_packages(package)` (optional) — packages visible without an
  import, closest first. Default: the file's own package. C# returns every
  parent namespace and the global one.

A `ParsedFile` holds:

- `package` — the grouping unit (package, namespace, module path...), `.`
  separated, or `None`. It may come from the text or from
  `source.relative_path`.
- `declarations` — one `TypeDecl` per UML classifier: `name`, `kind`
  (`CLASS`, `INTERFACE` or `ENUM`), `stereotype` (your label for what it
  really is: `<<record>>`, `<<module>>`, `<<trait>>`...), `is_abstract`,
  `members` (`Member`: kind, name, visibility, static/abstract flags,
  display type, parameter texts), `enum_values`. A file with no
  declarations is still linked (it may extend types declared elsewhere) but
  gets no diagram.
- `hints` — where the file's names come from: `type_imports` (name ->
  package) and `namespace_imports` (packages imported whole). Used to place
  relation ends in their package.
- `facts` — yours; the core never reads it.

`Relation(source, arrow, target, level, multiplicity)` uses bare names and
the arrows in `docgen.core.relations` (`INHERITS`, `REALIZES`, `COMPOSES`,
`AGGREGATES`, `ASSOCIATES`, `DEPENDS`). `level` decides the views: base
views show `INHERITANCE` and `STRONG`, full views everything. The core finds
each end's package from its name (`hints`, then the project); when your
language knows exactly where the target is declared, pass
`target_package=` (`None` for no package) and the lookup is skipped —
needed when the target shares its name with a declaration of the file
itself (Python: `python/language.py` using `oo/language.py`).

Stereotypes need a color: pass a `StereotypeStyle` for each of yours to
`skinparam_lines` (`style.MODULE_STYLE` exists for module boxes).

## The object-oriented route (`docgen/oo`)

Subclass `docgen.oo.language.ObjectOrientedLanguage`. Its `link` infers
relations from one `TypeFacts` per declaration. Build each file with
`object_oriented_file(stem, package, hints, types)`, where `types` pairs each
`TypeDecl` with its `TypeFacts`:

- `name`, `base_class`, `additional_bases` (multiple inheritance),
  `interfaces` — type texts as written; a base must be a simple name.
- `field_usages` (`FieldUsage`: type text, public?, serialized?),
  `signature_types`, `body_types`, `newed_types`. Leave them empty for a
  type that should get no usage relations (enums and interfaces do).

Extra class attributes:

| Attribute | Example |
|---|---|
| `vocabulary` | `TypeVocabulary(primitives=..., collection_wrappers=...)`; `type_argument_brackets=("[", "]")` if the language writes `list[Foo]` |
| `hidden_bases` (optional) | base classes never drawn, e.g. Unity's `MonoBehaviour` |

Override `relation_policy(project)` to change how a held type becomes a
relation (Unity: ScriptableObject fields are aggregation). It receives the
whole project, so it can depend on every file.

`docgen.oo.stereotypes.class_stereotype(modifiers, kind_stereotype)` gives
the shared labels (`<<record>>`, `<<struct>>`, `<<abstract>>`,
`<<static>>`).

## Helpers for brace languages

`docgen/clike/` holds scanning helpers shared by Java and C#: comment
stripping, brace matching, depth-aware splitting, flattening a type body
into member statements, and scanning method bodies for used types. A
language with other syntax doesn't need them: `docgen/languages/python/`
uses Python's own `ast` module.
