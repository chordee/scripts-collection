"""Shared pytest setup for MAYA utils tests.

These tests exercise pure-``pxr`` logic (no ``maya.cmds``, no Maya session
required), so they're run here under Houdini's ``hython`` purely as a
convenient local Python with ``pxr`` available — the code under test never
touches anything Houdini-specific.
"""

import os
import sys

PACKAGE_PARENT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PACKAGE_PARENT not in sys.path:
    sys.path.insert(0, PACKAGE_PARENT)
