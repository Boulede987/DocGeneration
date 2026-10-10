#!/usr/bin/env python3
"""
generate_class_diagramm_java.py
Reads every .java file under one or more <src_dir> trees and writes, under
the output root (default: <first src_dir>/Modelisation):
  ClassDiagram/       — one .puml per file: extends/implements + composition
  Fragments/          — fragment versions (no @startuml/@enduml)
  ClassDiagram-Full/  — same + association (-->) and dependency (..>)
  Fragments-Full/     — fragment versions of the full diagrams
  Packages/           — one diagram per package, _overview.puml, _project.puml
  Packages-Full/      — same views with every relation

Pass every module's source root (e.g. a Gradle multi-module project) in one
invocation so cross-module relations and the package views are complete.
"""

import sys

from docgen.core.cli import main
from docgen.languages import REGISTRY

sys.exit(main(REGISTRY["java"]))
