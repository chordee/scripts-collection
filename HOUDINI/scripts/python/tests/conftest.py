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

import pytest

# Make ``from chd_toolkits.<sub> import ...`` work regardless of the cwd
# pytest is invoked from (the pyproject.toml's pythonpath entry also handles
# this when pytest is run from HOUDINI/scripts/python/, but the conftest
# fallback is harmless).
PACKAGE_PARENT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PACKAGE_PARENT not in sys.path:
    sys.path.insert(0, PACKAGE_PARENT)


@pytest.fixture(autouse=True)
def _clear_hipfile_between_tests():
    """Reset Houdini's hip scene between tests so DAG/playbar state does not leak.

    Plain Python (no ``hou``) is a no-op. Inside hython, ``hipFile.clear`` is
    cheap and prevents tests from polluting each other when they create OBJ
    subnets, cameras, or modify the playbar (e.g. ``nerfstudio_cam``).
    """
    yield
    try:
        import hou
    except ImportError:
        return
    hou.hipFile.clear(suppress_save_prompt=True)


class MockSopNode:
    """Minimal ``hou.SopNode`` stand-in for helpers that only call ``.geometry()``.

    Used by tests that exercise functions like
    :func:`chd_toolkits.colmap_points.read_points3d_binary_to_geo` whose
    signature requires a ``parent_node`` even though the only API they touch
    on it is ``.geometry()``. Building a real Python SOP would require
    cooking and DAG state we don't need.
    """

    def __init__(self) -> None:
        import hou  # deferred until hython is present
        self._geo = hou.Geometry()

    def geometry(self):  # noqa: D401 - matches hou.SopNode.geometry()
        return self._geo
