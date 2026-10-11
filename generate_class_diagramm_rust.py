#!/usr/bin/env python3
"""
generate_class_diagramm_rust.py
Reads every .rs file under one or more <src_dir> trees and writes, under
the output root (default: <first src_dir>/Modelisation):
  ClassDiagram/       — one .puml per file: inheritance + composition
  Fragments/          — fragment versions (no @startuml/@enduml)
  ClassDiagram-Full/  — same + association (-->) and dependency (..>)
  Fragments-Full/     — fragment versions of the full diagrams
  Modules/            — one diagram per module, _overview.puml, _project.puml
  Modules-Full/       — same views with every relation

Pass the crate's src/ folder: lib.rs (or main.rs) there is the crate root,
and a file's module is its path from that folder. Needs tree-sitter
(python -m pip install -r requirements.txt).
"""

import sys

from docgen.core.cli import main
from docgen.languages import REGISTRY

sys.exit(main(REGISTRY["rust"]))
