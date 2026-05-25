"""Tests for chd_toolkits.nerfstudio_cam.create_animated_camera.

Each test gets a clean ``hipFile`` via the autouse fixture in conftest.py,
so the OBJ subnet / camera / playbar mutations do not leak between tests.
"""

import json

import pytest

pytest.importorskip("hou")

import hou

from chd_toolkits.nerfstudio_cam import create_animated_camera


def _write_transforms_json(path, frames=3, w=1920, h=1080, fl_x=1200.0):
    """Write a minimal Nerfstudio ``transforms.json``.

    Frames are numbered 1..``frames`` (extracted from ``file_path``) and use a
    translation of ``(frame, 0, 0)`` so each test can assert against a known
    keyframe value.
    """
    data = {
        "w": w,
        "h": h,
        "fl_x": fl_x,
        "frames": [
            {
                "file_path": f"./images/frame_{i:04d}.png",
                "transform_matrix": [
                    [1.0, 0.0, 0.0, float(i)],
                    [0.0, 1.0, 0.0, 0.0],
                    [0.0, 0.0, 1.0, 0.0],
                    [0.0, 0.0, 0.0, 1.0],
                ],
            }
            for i in range(1, frames + 1)
        ],
    }
    with open(path, "w") as f:
        json.dump(data, f)


# ---------------------------------------------------------------------------


def test_create_animated_camera_creates_node(tmp_path):
    json_path = tmp_path / "transforms.json"
    _write_transforms_json(json_path, frames=3)

    cam = create_animated_camera(str(json_path), cam_name="TestCam")
    assert cam is not None
    assert isinstance(cam, hou.ObjNode)
    assert cam.name() == "TestCam"
    # Parent should be the default 'NeRF_Import' subnet.
    assert cam.parent().name() == "NeRF_Import"


def test_create_animated_camera_custom_subnet_name(tmp_path):
    json_path = tmp_path / "transforms.json"
    _write_transforms_json(json_path, frames=2)

    cam = create_animated_camera(
        str(json_path),
        cam_name="MyCam",
        subnet_name="MySubnet",
    )
    assert cam.parent().name() == "MySubnet"


def test_create_animated_camera_focal_length():
    """focal_mm = (fl_x / w) * aperture_width."""
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        json_path = f"{td}/transforms.json"
        _write_transforms_json(json_path, frames=1, w=1920, fl_x=960.0)
        cam = create_animated_camera(str(json_path), aperture_width=36.0)
        # (960 / 1920) * 36 = 18.0
        assert cam.parm("focal").eval() == pytest.approx(18.0)


def test_create_animated_camera_resolution(tmp_path):
    json_path = tmp_path / "transforms.json"
    _write_transforms_json(json_path, frames=1, w=2048, h=1080)

    cam = create_animated_camera(str(json_path))
    assert cam.parm("resx").eval() == pytest.approx(2048)
    assert cam.parm("resy").eval() == pytest.approx(1080)


def test_create_animated_camera_writes_keyframes_on_all_channels(tmp_path):
    json_path = tmp_path / "transforms.json"
    _write_transforms_json(json_path, frames=5)

    cam = create_animated_camera(str(json_path))

    for channel in ("tx", "ty", "tz", "rx", "ry", "rz"):
        keys = cam.parm(channel).keyframes()
        assert len(keys) == 5, f"{channel} expected 5 keyframes, got {len(keys)}"


def test_create_animated_camera_translation_per_frame(tmp_path):
    """transform_matrix translation column ends up on tx after transpose."""
    json_path = tmp_path / "transforms.json"
    _write_transforms_json(json_path, frames=3)

    cam = create_animated_camera(str(json_path))
    tx_keys = cam.parm("tx").keyframes()
    # frames 1..3 → tx 1, 2, 3
    frame_to_value = {int(k.frame()): k.value() for k in tx_keys}
    assert frame_to_value[1] == pytest.approx(1.0)
    assert frame_to_value[2] == pytest.approx(2.0)
    assert frame_to_value[3] == pytest.approx(3.0)


def test_create_animated_camera_sets_playbar_range(tmp_path):
    json_path = tmp_path / "transforms.json"
    _write_transforms_json(json_path, frames=10)

    create_animated_camera(str(json_path))
    start, end = hou.playbar.frameRange()
    assert int(start) == 1
    assert int(end) == 10


def test_create_animated_camera_missing_file_returns_none(tmp_path):
    result = create_animated_camera(str(tmp_path / "missing.json"))
    assert result is None


def test_create_animated_camera_empty_frames_returns_none(tmp_path):
    json_path = tmp_path / "transforms.json"
    with open(json_path, "w") as f:
        json.dump({"w": 1920, "h": 1080, "fl_x": 1000.0, "frames": []}, f)
    result = create_animated_camera(str(json_path))
    assert result is None


def test_create_animated_camera_replaces_existing_node(tmp_path):
    """Calling twice with the same cam_name should destroy + rebuild."""
    json_path = tmp_path / "transforms.json"
    _write_transforms_json(json_path, frames=2)

    cam1 = create_animated_camera(str(json_path), cam_name="DupCam")
    cam2 = create_animated_camera(str(json_path), cam_name="DupCam")

    # cam2 lives at the expected path.
    assert cam2.path() == "/obj/NeRF_Import/DupCam"
    # cam1's underlying node was destroyed; accessing it raises ObjectWasDeleted.
    with pytest.raises(hou.ObjectWasDeleted):
        cam1.name()
    # Exactly one camera with this name (no leftover duplicates).
    siblings = [c for c in cam2.parent().children() if c.name() == "DupCam"]
    assert len(siblings) == 1
