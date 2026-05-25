"""Nerfstudio ``transforms.json`` → Houdini animated camera."""

import json
import os
import re
from typing import Any, Dict, Optional

import hou


_DEFAULT_SUBNET_NAME = "NeRF_Import"


def _get_frame_num(frame_data: Dict[str, Any]) -> int:
    """Extract the integer frame number embedded in ``frame_data['file_path']``."""
    fname = os.path.basename(frame_data["file_path"])
    match = re.search(r"(\d+)", fname)
    return int(match.group(1)) if match else 0


def create_animated_camera(
    json_path: str,
    global_scale: float = 1.0,
    cam_name: str = "Nerfstudio_Animated_Cam",
    aperture_width: float = 36.0,
    subnet_name: str = _DEFAULT_SUBNET_NAME,
) -> Optional[hou.ObjNode]:
    """Build a keyframed Houdini camera from a Nerfstudio ``transforms.json``.

    Args:
        json_path: Path to the Nerfstudio JSON file.
        global_scale: Scalar applied to translation values.
        cam_name: Camera node name (recreated if already present).
        aperture_width: Aperture (mm) used together with the JSON's
            ``fl_x`` / ``w`` to compute focal length in mm.
        subnet_name: Name of the ``/obj`` subnet that holds the camera;
            created if it does not exist.

    Returns:
        The created camera node, or ``None`` if the file is missing or
        contains no frames.
    """
    if not os.path.isfile(json_path):
        hou.ui.displayMessage(f"Error: File not found at:\n{json_path}")
        return None

    print(f"Loading JSON: {json_path}")
    with open(json_path, "r") as f:
        data = json.load(f)

    frames = data.get("frames", [])
    frames.sort(key=_get_frame_num)

    if not frames:
        print("No frames found in JSON.")
        return None

    img_w = float(data.get("w", 1920))
    img_h = float(data.get("h", 1080))
    fl_x = float(data.get("fl_x", 1000))  # focal length in pixels
    focal_mm = (fl_x / img_w) * aperture_width

    obj = hou.node("/obj")
    subnet = obj.node(subnet_name) or obj.createNode("subnet", subnet_name)

    cam = subnet.node(cam_name)
    if cam:
        cam.destroy()
    cam = subnet.createNode("cam", cam_name)

    print(f"Creating animation for {len(frames)} frames...")

    cam.parm("resx").set(img_w)
    cam.parm("resy").set(img_h)
    cam.parm("aperture").set(aperture_width)
    cam.parm("focal").set(focal_mm)
    cam.parm("iconscale").set(0.5)

    # Reserved for future coordinate-system corrections (currently identity).
    correction_rot = hou.hmath.buildRotate(0, 0, 0)

    with hou.undos.group("Import Nerfstudio Camera"):
        for frame_data in frames:
            f_num = _get_frame_num(frame_data)
            raw_mtx = frame_data["transform_matrix"]

            if isinstance(raw_mtx[0], list):
                flat_mtx = [v for row in raw_mtx for v in row]
            else:
                flat_mtx = raw_mtx

            # Column-major (Nerfstudio) -> row-major (Houdini)
            h_mtx = hou.Matrix4(tuple(flat_mtx)).transposed()
            final_mtx = h_mtx * correction_rot

            tra = final_mtx.extractTranslates()
            rot = final_mtx.extractRotates()

            values = (
                tra[0] * global_scale,
                tra[1] * global_scale,
                tra[2] * global_scale,
                rot[0],
                rot[1],
                rot[2],
            )

            for p_name, val in zip(("tx", "ty", "tz", "rx", "ry", "rz"), values):
                k = hou.Keyframe()
                k.setFrame(f_num)
                k.setValue(val)
                k.setExpression("linear()")
                cam.parm(p_name).setKeyframe(k)

    start_frame = _get_frame_num(frames[0])
    end_frame = _get_frame_num(frames[-1])
    hou.playbar.setFrameRange(start_frame, end_frame)
    hou.playbar.setPlaybackRange(start_frame, end_frame)
    hou.setFrame(start_frame)

    subnet.layoutChildren()
    print(f"Success! Animated camera created at: {cam.path()}")
    return cam
