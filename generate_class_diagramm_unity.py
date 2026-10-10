#!/usr/bin/env python3
"""
generate_class_diagramm_unity.py
Unity-flavored C# class diagrams: same outputs as generate_class_diagramm.py,
plus Unity conventions — engine base classes (MonoBehaviour...) not drawn,
<<scriptableObject>> stereotype, ScriptableObject fields as aggregation,
[SerializeField] fields as composition.

Usage: generate_class_diagramm_unity.py SRC_DIR [SRC_DIR ...] [-o OUT]
       generate_class_diagramm_unity.py SRC_DIR OUT_DIR   (legacy form)
"""

import sys

from docgen.core.cli import main
from docgen.languages import REGISTRY

sys.exit(main(REGISTRY["unity"], legacy_out_positional=True))
