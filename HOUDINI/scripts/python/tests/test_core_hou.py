"""Tests for chd_toolkits.core helpers that need real ``hou`` objects.

Covers ``matrix_manipulate``, ``primitive_xform``, ``point_attrib_to_numpy``.
Requires hython.
"""

import numpy as np
import pytest

pytest.importorskip("hou")
pytest.importorskip("pxr")

import hou
from pxr import Usd, UsdGeom

from chd_toolkits.core import (
    matrix_manipulate,
    point_attrib_to_numpy,
    primitive_xform,
)


# ---------------------------------------------------------------------------
# matrix_manipulate
# ---------------------------------------------------------------------------


def test_matrix_manipulate_identity_returns_input():
    mat = hou.Matrix4(1.0)  # identity
    data = np.array([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]], dtype=np.float32)
    out = matrix_manipulate(mat, data)
    assert out is not None
    np.testing.assert_allclose(out, data, rtol=1e-5)


def test_matrix_manipulate_translate():
    mat = hou.hmath.buildTranslate((10.0, 20.0, 30.0))
    data = np.array([[1.0, 2.0, 3.0]], dtype=np.float32)
    out = matrix_manipulate(mat, data)
    np.testing.assert_allclose(out, [[11.0, 22.0, 33.0]], rtol=1e-5)


def test_matrix_manipulate_matrix3_is_promoted():
    mat = hou.Matrix3(1.0)
    data = np.array([[5.0, 6.0, 7.0]], dtype=np.float32)
    out = matrix_manipulate(mat, data)
    assert out is not None
    np.testing.assert_allclose(out, data, rtol=1e-5)


def test_matrix_manipulate_rejects_1d_input():
    mat = hou.Matrix4(1.0)
    data_1d = np.array([1.0, 2.0, 3.0], dtype=np.float32)
    assert matrix_manipulate(mat, data_1d) is None


def test_matrix_manipulate_rejects_wrong_column_count():
    mat = hou.Matrix4(1.0)
    data = np.array([[1.0, 2.0]], dtype=np.float32)
    assert matrix_manipulate(mat, data) is None


# ---------------------------------------------------------------------------
# primitive_xform
# ---------------------------------------------------------------------------


def test_primitive_xform_identity_returns_identity_matrix():
    stage = Usd.Stage.CreateInMemory()
    xform = UsdGeom.Xform.Define(stage, "/X")
    result = primitive_xform(xform.GetPrim())
    assert isinstance(result, hou.Matrix4)
    identity = hou.Matrix4(1.0)
    for i in range(4):
        for j in range(4):
            assert result.at(i, j) == pytest.approx(identity.at(i, j))


def test_primitive_xform_translate_lands_in_row_3():
    stage = Usd.Stage.CreateInMemory()
    xform = UsdGeom.Xform.Define(stage, "/X")
    xform.AddTranslateOp().Set((10.0, 20.0, 30.0))
    result = primitive_xform(xform.GetPrim())
    # Houdini Matrix4 stores translation in row 3.
    assert result.at(3, 0) == pytest.approx(10.0)
    assert result.at(3, 1) == pytest.approx(20.0)
    assert result.at(3, 2) == pytest.approx(30.0)


def test_primitive_xform_accepts_int_time():
    stage = Usd.Stage.CreateInMemory()
    xform = UsdGeom.Xform.Define(stage, "/X")
    op = xform.AddTranslateOp()
    op.Set(time=1.0, value=(1.0, 0.0, 0.0))
    op.Set(time=2.0, value=(2.0, 0.0, 0.0))
    # int 2 should auto-wrap to Usd.TimeCode(2).
    result = primitive_xform(xform.GetPrim(), 2)
    assert result.at(3, 0) == pytest.approx(2.0)


# ---------------------------------------------------------------------------
# point_attrib_to_numpy
# ---------------------------------------------------------------------------


def test_point_attrib_to_numpy_reads_position():
    geo = hou.Geometry()
    for x in (1.0, 2.0, 3.0):
        pt = geo.createPoint()
        pt.setPosition((x, x * 2, x * 3))
    arr = point_attrib_to_numpy(geo, "P")
    assert arr is not None
    assert arr.dtype == np.float32
    assert arr.shape == (3, 3)
    np.testing.assert_allclose(arr[:, 0], [1.0, 2.0, 3.0])
    np.testing.assert_allclose(arr[:, 1], [2.0, 4.0, 6.0])
    np.testing.assert_allclose(arr[:, 2], [3.0, 6.0, 9.0])


def test_point_attrib_to_numpy_reads_int_attribute():
    geo = hou.Geometry()
    attr = geo.addAttrib(hou.attribType.Point, "id", 0)  # int default
    for i in range(5):
        pt = geo.createPoint()
        pt.setAttribValue(attr, i * 10)
    arr = point_attrib_to_numpy(geo, "id")
    assert arr is not None
    assert arr.dtype == np.int32
    np.testing.assert_array_equal(arr.flatten(), [0, 10, 20, 30, 40])


def test_point_attrib_to_numpy_missing_attribute_returns_none():
    geo = hou.Geometry()
    geo.createPoint()
    assert point_attrib_to_numpy(geo, "no_such_attr") is None
