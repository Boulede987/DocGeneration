#!/usr/bin/env python3
"""
generate_class_diagramm.py
Reads every .cs file under one or more <src_dir> trees and writes, under
the output root (default: <first src_dir>/Modelisation):
  ClassDiagram/       — one .puml per file: inherits/implements + composition
  Fragments/          — fragment versions (no @startuml/@enduml)
  ClassDiagram-Full/  — same + association (-->) and dependency (..>)
  Fragments-Full/     — fragment versions of the full diagrams
  Namespaces/         — one diagram per namespace, _overview.puml, _project.puml
  Namespaces-Full/    — same views with every relation

Usage: generate_class_diagramm.py SRC_DIR [SRC_DIR ...] [-o OUT]
       generate_class_diagramm.py SRC_DIR OUT_DIR   (legacy form)
"""

import sys

from docgen.core.cli import main
from docgen.languages import REGISTRY

sys.exit(main(REGISTRY["csharp"], legacy_out_positional=True))
