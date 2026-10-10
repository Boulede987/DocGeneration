#!/usr/bin/env python3
"""
generate_class_diagramm_python.py
Reads every .py file under one or more <src_dir> trees and writes, under
the output root (default: <first src_dir>/Modelisation):
  ClassDiagram/       — one .puml per module: inheritance + composition
  Fragments/          — fragment versions (no @startuml/@enduml)
  ClassDiagram-Full/  — same + association (-->) and dependency (..>)
  Fragments-Full/     — fragment versions of the full diagrams
  Packages/           — one diagram per package, _overview.puml, _project.puml
  Packages-Full/      — same views with every relation

Pass the folder that contains your top-level packages (e.g. src/): a
module's package is its folder path relative to that root.
"""

import sys

from docgen.core.cli import main
from docgen.languages import REGISTRY

sys.exit(main(REGISTRY["python"]))
