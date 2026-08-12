"""COLMAP ``.bin`` point cloud → Houdini geometry."""

import os
import struct
from typing import Optional

import hou


# Per-point binary record: POINT3D_ID(uint64) + XYZ(3*double) + RGB(3*uint8) + ERROR(double) = 43 bytes
_POINT_RECORD_FMT = "<QdddBBBd"
_POINT_RECORD_SIZE = 43


def _notify(message: str) -> None:
    """Show ``message`` via ``hou.ui`` if available; otherwise print to stdout.

    ``hou.ui`` is missing in headless hython / batch contexts, so the bare
    ``hou.ui.displayMessage`` call would crash with ``AttributeError``.
    """
    ui = getattr(hou, "ui", None)
    if ui is not None and hasattr(ui, "displayMessage"):
        ui.displayMessage(message)
    else:
        print(message)


def read_points3d_binary_to_geo(
    path_to_model_file: str,
    parent_node: hou.SopNode,
) -> Optional[int]:
    """Read a COLMAP ``points3D.bin`` into the geometry of a Python SOP.

    Args:
        path_to_model_file: Path to ``points3D.bin``.
        parent_node: The Python SOP whose geometry receives the points.

    Returns:
        Number of points written, or ``None`` if the file was missing or
        had an unsupported extension.
    """
    if not os.path.isfile(path_to_model_file):
        _notify(f"File not found: {path_to_model_file}")
        return None

    if not path_to_model_file.lower().endswith(".bin"):
        _notify(
            "Error: This script only supports COLMAP .bin format.\n"
            "If you want to read .ply, please use File SOP directly."
        )
        return None

    geo = parent_node.geometry()
    geo.clear()

    attr_cd = geo.addAttrib(hou.attribType.Point, "Cd", (0.0, 0.0, 0.0))
    attr_err = geo.addAttrib(hou.attribType.Point, "error", 0.0)

    print(f"Reading {path_to_model_file}...")

    points_written = 0
    with open(path_to_model_file, "rb") as fid:
        header = fid.read(8)
        if len(header) < 8:
            raise ValueError("File is too small or empty.")
        num_points = struct.unpack("<Q", header)[0]
        print(f"Total points to read: {num_points}")

        with hou.InterruptableOperation(
            "Importing COLMAP Points", open_interrupt_dialog=True
        ) as operation:
            for i in range(num_points):
                if i % 1000 == 0:
                    operation.updateProgress(float(i) / num_points if num_points else 0.0)

                record = fid.read(_POINT_RECORD_SIZE)
                if len(record) < _POINT_RECORD_SIZE:
                    geo.clear()
                    raise ValueError(
                        f"Truncated file: header declares {num_points} point(s) but "
                        f"point {i} is incomplete ({len(record)}/{_POINT_RECORD_SIZE} "
                        "bytes) — the file was likely cut off during transfer."
                    )

                data = struct.unpack(_POINT_RECORD_FMT, record)
                # data[0] is point3D_id (unused).
                xyz = (data[1], data[2], data[3])
                rgb = (data[4] / 255.0, data[5] / 255.0, data[6] / 255.0)
                error = data[7]

                track_len_data = fid.read(8)
                if len(track_len_data) < 8:
                    geo.clear()
                    raise ValueError(
                        f"Truncated file: header declares {num_points} point(s) but "
                        f"the track-length field for point {i} is incomplete — the "
                        "file was likely cut off during transfer."
                    )
                track_length = struct.unpack("<Q", track_len_data)[0]
                # Each track element = 2 * uint32 = 8 bytes; skip from current position.
                fid.seek(track_length * 8, 1)

                pt = geo.createPoint()
                # Coordinate system left as-authored; downstream Transform SOP can
                # convert NeRF Z-up -> Houdini Y-up if needed.
                pt.setPosition(xyz)
                pt.setAttribValue(attr_cd, rgb)
                pt.setAttribValue(attr_err, error)
                points_written += 1

    print("Done.")
    return points_written
