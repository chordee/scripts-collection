"""Shared pytest setup for chd_toolkits tests.

These tests are primarily designed to run inside Houdini's ``hython`` so the
``pxr`` modules under test are exactly the build Houdini ships with. Use
``python tests/run_hython.py`` (with ``HFS`` set) to invoke them.

Tests that only depend on ``pxr`` (currently the ``stitch_usd_clips`` suite)
can also run in plain Python with ``pip install pytest usd-core``; the other
suites will be skipped automatically.
"""

import os
import sys

# Make ``from chd_toolkits.<sub> import ...`` work regardless of the cwd
# pytest is invoked from (the pyproject.toml's pythonpath entry also handles
# this when pytest is run from HOUDINI/scripts/python/, but the conftest
# fallback is harmless).
PACKAGE_PARENT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PACKAGE_PARENT not in sys.path:
    sys.path.insert(0, PACKAGE_PARENT)
