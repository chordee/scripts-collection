"""Run this directory's tests inside Nuke, where PySide6 and a QApplication exist.

Usage:
    Nuke17.0.exe --tg NUKE/python/tests/run_tests.py
"""

import os
import sys
import unittest

here = os.path.dirname(os.path.abspath(__file__))
suite = unittest.defaultTestLoader.discover(here)
result = unittest.TextTestRunner(verbosity=1).run(suite)
sys.exit(0 if result.wasSuccessful() else 1)
