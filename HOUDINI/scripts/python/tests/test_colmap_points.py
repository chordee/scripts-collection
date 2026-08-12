"""Tests for chd_toolkits.colmap_points.read_points3d_binary_to_geo.

Builds a minimal COLMAP ``points3D.bin`` on disk, then runs the helper
with a MockSopNode whose ``.geometry()`` returns a standalone
``hou.Geometry`` we can inspect.
"""

import struct

import pytest

pytest.importorskip("hou")

import hou

from chd_toolkits.colmap_points import read_points3d_binary_to_geo

from conftest import MockSopNode


def _write_colmap_bin(path, points):
    """Write a COLMAP ``points3D.bin``.

    ``points`` is a list of ``(point3D_id, x, y, z, r, g, b, error, track_length)``
    tuples. Track contents are written as zeros (their identity does not
    matter; the reader only seeks past them).
    """
    with open(path, "wb") as fid:
        fid.write(struct.pack("<Q", len(points)))
        for pid, x, y, z, r, g, b, err, track_len in points:
            fid.write(struct.pack("<QdddBBBd", pid, x, y, z, r, g, b, err))
            fid.write(struct.pack("<Q", track_len))
            # Each track element = 2 * uint32 = 8 bytes.
            fid.write(b"\x00" * (track_len * 8))


# ---------------------------------------------------------------------------


def test_read_points3d_writes_position_and_color(tmp_path):
    bin_path = tmp_path / "points3D.bin"
    _write_colmap_bin(
        bin_path,
        [
            (1, 0.0, 0.0, 0.0, 255, 0, 0, 0.5, 0),
            (2, 1.0, 2.0, 3.0, 0, 255, 0, 0.7, 0),
            (3, -1.0, -2.0, -3.0, 0, 0, 255, 0.9, 0),
        ],
    )

    node = MockSopNode()
    result = read_points3d_binary_to_geo(str(bin_path), node)
    assert result == 3

    geo = node.geometry()
    points = geo.points()
    assert len(points) == 3

    # hou.Vector3 doesn't compare directly with pytest.approx — convert to tuple.
    assert tuple(points[0].position()) == pytest.approx((0.0, 0.0, 0.0))
    assert tuple(points[1].position()) == pytest.approx((1.0, 2.0, 3.0))
    assert tuple(points[2].position()) == pytest.approx((-1.0, -2.0, -3.0))

    # Cd should be normalized 0..1
    assert tuple(points[0].attribValue("Cd")) == pytest.approx((1.0, 0.0, 0.0))
    assert tuple(points[1].attribValue("Cd")) == pytest.approx((0.0, 1.0, 0.0))
    assert tuple(points[2].attribValue("Cd")) == pytest.approx((0.0, 0.0, 1.0))

    assert points[0].attribValue("error") == pytest.approx(0.5)
    assert points[2].attribValue("error") == pytest.approx(0.9)


def test_read_points3d_skips_track_bytes(tmp_path):
    """Tracks of varying length must be skipped without throwing off the read offset."""
    bin_path = tmp_path / "points3D.bin"
    _write_colmap_bin(
        bin_path,
        [
            (1, 0.0, 0.0, 0.0, 255, 255, 255, 0.0, 5),  # 5 track entries
            (2, 9.0, 9.0, 9.0, 128, 128, 128, 0.0, 0),
        ],
    )

    node = MockSopNode()
    result = read_points3d_binary_to_geo(str(bin_path), node)
    assert result == 2

    points = node.geometry().points()
    # The second point's position should still parse correctly despite the
    # variable-length track on the first point.
    assert tuple(points[1].position()) == pytest.approx((9.0, 9.0, 9.0))


def test_read_points3d_clears_existing_geometry(tmp_path):
    """The function should call geo.clear() before adding new points."""
    bin_path = tmp_path / "points3D.bin"
    _write_colmap_bin(bin_path, [(1, 0.0, 0.0, 0.0, 0, 0, 0, 0.0, 0)])

    node = MockSopNode()
    # Seed the geometry with pre-existing points the function should remove.
    pre_geo = node.geometry()
    pre_geo.createPoint()
    pre_geo.createPoint()
    assert len(pre_geo.points()) == 2

    read_points3d_binary_to_geo(str(bin_path), node)
    assert len(node.geometry().points()) == 1


def test_read_points3d_missing_file_returns_none(tmp_path):
    node = MockSopNode()
    result = read_points3d_binary_to_geo(str(tmp_path / "nope.bin"), node)
    assert result is None


def test_read_points3d_rejects_non_bin_extension(tmp_path):
    bad = tmp_path / "points3D.ply"
    bad.write_text("dummy")
    node = MockSopNode()
    result = read_points3d_binary_to_geo(str(bad), node)
    assert result is None


def test_read_points3d_truncated_record_raises(tmp_path):
    """A file whose header overstates the point count (cut off mid-transfer)
    must raise, not silently return a partial point count as if it succeeded.
    """
    bin_path = tmp_path / "points3D.bin"
    with open(bin_path, "wb") as fid:
        fid.write(struct.pack("<Q", 5))  # header claims 5 points
        for pid in range(2):
            fid.write(struct.pack("<QdddBBBd", pid, 0.0, 0.0, 0.0, 0, 0, 0, 0.0))
            fid.write(struct.pack("<Q", 0))
        fid.write(struct.pack("<Qdd", 99, 1.0, 2.0))  # incomplete 3rd record

    node = MockSopNode()
    with pytest.raises(ValueError, match="Truncated"):
        read_points3d_binary_to_geo(str(bin_path), node)

    # Geometry must be left empty, not half-populated with the 2 valid points.
    assert len(node.geometry().points()) == 0


def test_read_points3d_truncated_track_length_raises(tmp_path):
    bin_path = tmp_path / "points3D.bin"
    with open(bin_path, "wb") as fid:
        fid.write(struct.pack("<Q", 2))  # header claims 2 points
        fid.write(struct.pack("<QdddBBBd", 1, 0.0, 0.0, 0.0, 0, 0, 0, 0.0))
        fid.write(b"\x00\x00\x00")  # incomplete track-length field (needs 8 bytes)

    node = MockSopNode()
    with pytest.raises(ValueError, match="Truncated"):
        read_points3d_binary_to_geo(str(bin_path), node)
    assert len(node.geometry().points()) == 0
