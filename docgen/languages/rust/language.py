from typing import Mapping

from docgen.core.language import Language
from docgen.core.model import ParsedFile, ResolutionHints, SourceText
from docgen.core.project import Project
from docgen.core.relations import Relation

from .facts import RustFacts
from .index import CrateIndex
from .items import parse_items
from .linking import file_relations, merge_impls
from .modules import module_path_of, use_bindings
from .syntax import parse_tree
from .vocabulary import RUST_VOCABULARY, SKINPARAM_LINES


class RustLanguage(Language[RustFacts]):
    """Parsed with tree-sitter. A file's module comes from its place in the
    crate (lib.rs is the root). Every relation is resolved here, with Rust's
    own path rules, and given its target's module: the core never guesses
    where a Rust type is."""
    name = "rust"
    source_suffix = ".rs"
    views_dir = "Modules"
    skinparam_lines = SKINPARAM_LINES
    vocabulary = RUST_VOCABULARY

    def parse_file(self, source: SourceText) -> ParsedFile[RustFacts]:
        root = parse_tree(source.text)
        module_path = module_path_of(source.relative_path)
        items = parse_items(root, module_path, use_bindings(root), self.vocabulary)
        return ParsedFile(
            stem=source.stem,
            package=module_path,
            declarations=items.declarations,
            hints=ResolutionHints(),
            facts=items.facts,
        )

    def link(self, project: Project[RustFacts]) -> Mapping[ParsedFile[RustFacts], list[Relation]]:
        """Impl blocks first, so their methods and references count for
        their type wherever it is declared."""
        index = CrateIndex(project)
        links = merge_impls(project, index)
        return {parsed: file_relations(parsed, links, index) for parsed in project.files}
