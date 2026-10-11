"""Where a name written in a Rust file is declared in the crate, following
Rust's own rules: paths (crate::, self::, super::), use declarations
(renamed and glob), then the file's own module. Anything else (std,
external crates) is unknown and draws nothing."""

from dataclasses import dataclass

from docgen.core.model import ParsedFile, TypeDecl
from docgen.core.project import Project

from .facts import ItemUse, RustFacts, RustTypeFacts
from .modules import CRATE, MODULE_SEPARATOR, PARENT_MODULE, SELF_MODULE
from .syntax import PATH_SEPARATOR, SELF_TYPE

_MODULE_KEYWORDS = frozenset({CRATE, SELF_MODULE, PARENT_MODULE})


@dataclass(frozen=True)
class TypeRef:
    """A declaration's place in the crate: its module (None: crate root)
    and its bare name."""
    module: str | None
    name: str


@dataclass(frozen=True)
class Declared:
    parsed: ParsedFile[RustFacts]
    declaration: TypeDecl
    facts: RustTypeFacts


@dataclass(frozen=True)
class ModuleBox:
    """A module's <<module>> box and the free items it shows."""
    ref: TypeRef
    member_names: frozenset[str]


def _module_key(segments: list[str]) -> str | None:
    return MODULE_SEPARATOR.join(segments) if segments else None


def _absolute(path: list[str], module: str | None, scope: tuple[str, ...] = ()) -> list[str] | None:
    """The crate-absolute path of a path written in 'module': crate:: from
    the root, self:: from the module, super:: one module up per super,
    anything else from the module itself (or an external crate: then it
    matches nothing). None when super climbs above the crate root."""
    here = (module.split(MODULE_SEPARATOR) if module else []) + list(scope)
    if path[0] == CRATE:
        return path[1:]
    if path[0] == SELF_MODULE:
        return here + path[1:]
    climbs = next((index for index, segment in enumerate(path) if segment != PARENT_MODULE), len(path))
    if climbs > len(here):
        return None
    return here[:len(here) - climbs] + path[climbs:]


class CrateIndex:
    """Every declared type and <<module>> box of the crate."""

    def __init__(self, project: Project[RustFacts]):
        self._declared: dict[TypeRef, Declared] = {}
        self._boxes: dict[str | None, ModuleBox] = {}
        # An inline module's items are drawn in its file's module.
        self._drawn_in: dict[str, str | None] = {}
        for parsed in project.files:
            self._index_file(parsed)

    def _index_file(self, parsed: ParsedFile[RustFacts]) -> None:
        facts = parsed.facts
        if facts is None:
            return
        for inline in facts.inline_modules:
            self._drawn_in[MODULE_SEPARATOR.join(filter(None, (facts.module_path, inline)))] = facts.module_path
        for declaration, type_facts in zip(parsed.declarations, facts.types, strict=True):
            ref = TypeRef(facts.module_path, declaration.bare_name)
            self._declared[ref] = Declared(parsed, declaration, type_facts)
            if declaration.name == facts.box_name:
                self._boxes[facts.module_path] = ModuleBox(ref, frozenset(member.name for member in declaration.members))

    def _module(self, segments: list[str]) -> str | None:
        key = _module_key(segments)
        return self._drawn_in.get(key, key) if key is not None else None

    def declared(self, ref: TypeRef) -> Declared | None:
        return self._declared.get(ref)

    def _bound_path(self, local_name: str, facts: RustFacts) -> list[str] | None:
        """What the last non-glob use declaration binding the name points to."""
        binding = next((use for use in reversed(facts.uses) if use.local_name == local_name and not use.is_glob), None)
        return _absolute(list(binding.path), facts.module_path, binding.scope) if binding is not None else None

    def _absolute_path(self, path: list[str], facts: RustFacts) -> list[str] | None:
        """A path whose first segment a use declaration binds goes through
        that binding; otherwise Rust's path rules apply."""
        if path[0] not in _MODULE_KEYWORDS and (bound := self._bound_path(path[0], facts)) is not None:
            return bound + path[1:]
        return _absolute(path, facts.module_path)

    def _glob_modules(self, facts: RustFacts) -> list[str | None]:
        return [
            self._module(absolute)
            for use in facts.uses if use.is_glob
            if (absolute := _absolute(list(use.path), facts.module_path, use.scope)) is not None
        ]

    def resolve_type(self, written: str, facts: RustFacts) -> TypeRef | None:
        path = written.split(PATH_SEPARATOR)
        if path == [SELF_TYPE]:
            return None
        if len(path) > 1 or self._bound_path(written, facts) is not None:
            absolute = self._absolute_path(path, facts)
            ref = TypeRef(self._module(absolute[:-1]), absolute[-1]) if absolute else None
            return ref if ref in self._declared else None
        own = TypeRef(facts.module_path, written)
        if own in self._declared:
            return own
        from_globs = [ref for module in self._glob_modules(facts) if (ref := TypeRef(module, written)) in self._declared]
        return from_globs[0] if len(from_globs) == 1 else None

    def _box_declaring(self, module: str | None, name: str) -> TypeRef | None:
        box = self._boxes.get(module)
        return box.ref if box is not None and name in box.member_names else None

    def resolve_item(self, use: ItemUse, facts: RustFacts) -> TypeRef | None:
        """The <<module>> box declaring the used function or constant: through
        its module path, a use declaration binding it, or exactly one glob."""
        if use.module_path is not None:
            absolute = self._absolute_path(use.module_path.split(PATH_SEPARATOR), facts)
            return self._box_declaring(self._module(absolute), use.name) if absolute is not None else None
        bound = self._bound_path(use.name, facts)
        if bound is not None:
            return self._box_declaring(self._module(bound[:-1]), bound[-1])
        from_globs = [box for module in self._glob_modules(facts) if (box := self._box_declaring(module, use.name))]
        return from_globs[0] if len(from_globs) == 1 else None
