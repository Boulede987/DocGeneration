"""What the Rust parser keeps about each file to link the crate once every
file is parsed. Names stay as written (paths included, e.g.
'crate::util::Money'): they can only be resolved with the whole crate
known. The containers are mutable on purpose: parsing fills them, linking
only reads them."""

from dataclasses import dataclass, field
from enum import Enum

from docgen.core.model import Member


class Ownership(Enum):
    """How a field holds a type: owned (by value, Box, collections) means
    the holder controls its lifetime; shared (&, &mut, Rc, Arc, Weak, raw
    pointers) means it doesn't."""
    OWNED = "owned"
    SHARED = "shared"


@dataclass(frozen=True)
class HeldType:
    """One named type inside a field's type, as written ('Tag' for
    Vec<Tag>, with is_collection set)."""
    name: str
    ownership: Ownership
    is_collection: bool


@dataclass(frozen=True)
class ItemUse:
    """A function, constant or static of another module, as written:
    module_path is the '::' path before the name ('pricing' in
    pricing::total), None when the name is used bare (brought in by a use
    declaration)."""
    module_path: str | None
    name: str


@dataclass(frozen=True)
class UseBinding:
    """local_name: the name a use declaration binds in the file (the alias
    with 'as'; empty for a glob, which binds every name of the module at
    'path'). path: the segments as written, crate/self/super included.
    scope: the inline module declaring it, relative to the file's module
    (empty at file level): self:: and super:: count from there."""
    local_name: str
    path: tuple[str, ...]
    is_glob: bool
    scope: tuple[str, ...] = ()


@dataclass
class RustTypeFacts:
    """One declaration's references. signature_types: types in parameters
    and return types; body_types: types mentioned in code. For a
    <<module>> box, fields and supertraits stay empty."""
    name: str
    fields: list[HeldType] = field(default_factory=list)
    supertraits: list[str] = field(default_factory=list)
    signature_types: list[str] = field(default_factory=list)
    body_types: list[str] = field(default_factory=list)
    item_uses: list[ItemUse] = field(default_factory=list)


@dataclass
class ImplBlock:
    """An impl block, merged into its target type at link time: the target
    may be declared in another file. target: the type's path as written."""
    target: str
    trait: str | None
    members: list[Member] = field(default_factory=list)
    signature_types: list[str] = field(default_factory=list)
    body_types: list[str] = field(default_factory=list)
    item_uses: list[ItemUse] = field(default_factory=list)


@dataclass
class RustFacts:
    """module_path: the file's module, None for the crate root. types[i]
    describes ParsedFile.declarations[i]. box_name: the file's <<module>>
    box, if it has free items. inline_modules: paths of its inline
    'mod x { }' blocks, relative to the file's module ('drafts', 'a.b'):
    their items are drawn in the file's module."""
    module_path: str | None
    types: list[RustTypeFacts] = field(default_factory=list)
    impl_blocks: list[ImplBlock] = field(default_factory=list)
    uses: list[UseBinding] = field(default_factory=list)
    box_name: str | None = None
    inline_modules: list[str] = field(default_factory=list)
