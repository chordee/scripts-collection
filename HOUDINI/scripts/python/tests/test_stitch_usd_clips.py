"""Tests for chd_toolkits.stitch_usd_clips.

Pure pxr module — runs in both hython and plain Python (the latter needs
``pip install usd-core``).
"""

import os

import pytest

# Skip the whole file if pxr is missing (plain Python without usd-core).
pytest.importorskip("pxr")
from pxr import Sdf, Usd, UsdGeom

from chd_toolkits.stitch_usd_clips import (
    build_clip_frame_lists,
    find_all_animated_prims,
    generate_manifest,
    generate_topology,
    resolve_filepath,
    stitch_clips,
    validate_files,
)


# ---------------------------------------------------------------------------
# resolve_filepath
# ---------------------------------------------------------------------------


def test_resolve_filepath_python_format():
    assert resolve_filepath("sim.{frame:04d}.usd", 5) == "sim.0005.usd"


def test_resolve_filepath_houdini_f4():
    assert resolve_filepath("sim.$F4.usd", 5) == "sim.0005.usd"


def test_resolve_filepath_houdini_f_no_padding():
    assert resolve_filepath("sim.$F.usd", 5) == "sim.5.usd"


def test_resolve_filepath_no_token():
    assert resolve_filepath("sim.usd", 5) == "sim.usd"


# ---------------------------------------------------------------------------
# build_clip_frame_lists
# ---------------------------------------------------------------------------


def test_build_clip_frame_lists_equal_ranges():
    scene, files = build_clip_frame_lists((1, 5), (1, 5), False)
    assert scene == [1, 2, 3, 4, 5]
    assert files == [1, 2, 3, 4, 5]


def test_build_clip_frame_lists_scene_shorter_truncates():
    scene, files = build_clip_frame_lists((1, 10), (1, 3), False)
    assert scene == [1, 2, 3]
    assert files == [1, 2, 3]


def test_build_clip_frame_lists_loop_repeats_file_frames():
    scene, files = build_clip_frame_lists((1, 3), (1, 8), True)
    assert scene == list(range(1, 9))
    assert files == [1, 2, 3, 1, 2, 3, 1, 2]


def test_build_clip_frame_lists_no_loop_truncates_to_files():
    # scene longer, loop=False: zip truncates to file length
    scene, files = build_clip_frame_lists((1, 3), (1, 8), False)
    assert scene == [1, 2, 3]
    assert files == [1, 2, 3]


# ---------------------------------------------------------------------------
# validate_files
# ---------------------------------------------------------------------------


def test_validate_files_all_present(tmp_path):
    paths = []
    for i in range(3):
        p = tmp_path / f"f{i}.usd"
        p.touch()
        paths.append(str(p))
    assert validate_files(paths) == []


def test_validate_files_missing_strict_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        validate_files([str(tmp_path / "nope.usd")], strict=True)


def test_validate_files_missing_non_strict_returns_list(tmp_path, capsys):
    missing = validate_files([str(tmp_path / "nope.usd")], strict=False)
    assert len(missing) == 1


# ---------------------------------------------------------------------------
# generate_topology / generate_manifest / find_all_animated_prims
# ---------------------------------------------------------------------------


@pytest.fixture
def animated_frame(tmp_path):
    """A single USD file with /Geo Xform + animated translate.

    Uses a top-level prim because ``generate_topology`` re-roots the copied
    hierarchy under ``/`` using the source prim's leaf name; nested paths
    like ``/World/Geo`` would round-trip to ``/Geo`` and confuse assertions.
    """
    path = str(tmp_path / "frame_1.usda")
    stage = Usd.Stage.CreateNew(path)
    xform = UsdGeom.Xform.Define(stage, "/Geo")
    op = xform.AddTranslateOp()
    op.Set(time=1.0, value=(1.0, 0, 0))
    op.Set(time=2.0, value=(2.0, 0, 0))
    stage.SetDefaultPrim(xform.GetPrim())
    stage.Save()
    return path


def test_generate_topology_writes_file_and_strips_timesamples(tmp_path, animated_frame):
    out = str(tmp_path / "topology.usda")
    generate_topology(animated_frame, "/Geo", out)
    assert os.path.exists(out)

    stage = Usd.Stage.Open(out)
    geo = stage.GetPrimAtPath("/Geo")
    assert geo.IsValid()
    translate_attr = geo.GetAttribute("xformOp:translate")
    if translate_attr.IsValid():
        assert translate_attr.GetNumTimeSamples() == 0


def test_generate_topology_sets_default_prim(tmp_path, animated_frame):
    out = str(tmp_path / "topology.usda")
    generate_topology(animated_frame, "/Geo", out)
    stage = Usd.Stage.Open(out)
    default = stage.GetDefaultPrim()
    assert default.IsValid()
    assert str(default.GetPath()) == "/Geo"


def test_generate_manifest_writes_file(tmp_path, animated_frame):
    out = str(tmp_path / "manifest.usda")
    generate_manifest(animated_frame, "/Geo", out)
    assert os.path.exists(out)


def test_find_all_animated_prims_finds_xform(animated_frame):
    paths = find_all_animated_prims(animated_frame, "/Geo")
    assert "/Geo" in paths


def test_find_all_animated_prims_returns_root_when_static(tmp_path):
    path = str(tmp_path / "static.usda")
    stage = Usd.Stage.CreateNew(path)
    UsdGeom.Xform.Define(stage, "/Geo")
    stage.Save()
    paths = find_all_animated_prims(path, "/Geo")
    assert paths == ["/Geo"]


def test_find_all_animated_prims_returns_root_when_path_missing(tmp_path):
    path = str(tmp_path / "empty.usda")
    Usd.Stage.CreateNew(path).Save()
    paths = find_all_animated_prims(path, "/Nope")
    assert paths == ["/Nope"]


# ---------------------------------------------------------------------------
# stitch_clips (integration)
# ---------------------------------------------------------------------------


@pytest.fixture
def frame_sequence(tmp_path):
    """3 per-frame USD files with animated translate at /World/Sim."""
    template = str(tmp_path / "sim.{frame:04d}.usda")
    for frame in (1, 2, 3):
        path = template.format(frame=frame)
        stage = Usd.Stage.CreateNew(path)
        xform = UsdGeom.Xform.Define(stage, "/World/Sim")
        op = xform.AddTranslateOp()
        op.Set(time=float(frame), value=(float(frame), 0, 0))
        stage.SetDefaultPrim(xform.GetPrim())
        stage.SetStartTimeCode(float(frame))
        stage.SetEndTimeCode(float(frame))
        stage.GetRootLayer().Save()
    return template


def test_stitch_clips_creates_output(tmp_path, frame_sequence):
    out = str(tmp_path / "stitched.usda")
    stitch_clips(
        filepath_template=frame_sequence,
        primpath="/World/Sim",
        output_path=out,
        frame_range=(1, 3),
    )
    assert os.path.exists(out)
    stage = Usd.Stage.Open(out)
    assert stage.GetPrimAtPath("/World/Sim").IsValid()


def test_stitch_clips_writes_clip_metadata(tmp_path, frame_sequence):
    out = str(tmp_path / "stitched.usda")
    stitch_clips(
        filepath_template=frame_sequence,
        primpath="/World/Sim",
        output_path=out,
        frame_range=(1, 3),
    )
    stage = Usd.Stage.Open(out)
    root = stage.GetPrimAtPath("/World/Sim")
    clip_api = Usd.ClipsAPI(root)
    asset_paths = clip_api.GetClipAssetPaths("default")
    assert len(asset_paths) == 3


def test_stitch_clips_writes_topology_and_manifest(tmp_path, frame_sequence):
    out = str(tmp_path / "stitched.usda")
    stitch_clips(
        filepath_template=frame_sequence,
        primpath="/World/Sim",
        output_path=out,
        frame_range=(1, 3),
    )
    assert os.path.exists(str(tmp_path / "stitched.topology.usda"))
    assert os.path.exists(str(tmp_path / "stitched.manifest.usda"))


def test_stitch_clips_no_topology_no_manifest(tmp_path, frame_sequence):
    out = str(tmp_path / "stitched.usda")
    stitch_clips(
        filepath_template=frame_sequence,
        primpath="/World/Sim",
        output_path=out,
        frame_range=(1, 3),
        gen_topology=False,
        gen_manifest=False,
    )
    assert not os.path.exists(str(tmp_path / "stitched.topology.usda"))
    assert not os.path.exists(str(tmp_path / "stitched.manifest.usda"))


def test_stitch_clips_probe_frame_out_of_range_raises(tmp_path, frame_sequence):
    with pytest.raises(ValueError):
        stitch_clips(
            filepath_template=frame_sequence,
            primpath="/World/Sim",
            output_path=str(tmp_path / "x.usda"),
            frame_range=(1, 3),
            probe_frame=99,
        )


def test_stitch_clips_probe_frame_missing_file_raises(tmp_path, frame_sequence):
    # probe_frame is in range, but no file at frame 5 (only 1..3 exist)
    with pytest.raises(FileNotFoundError):
        stitch_clips(
            filepath_template=frame_sequence,
            primpath="/World/Sim",
            output_path=str(tmp_path / "x.usda"),
            frame_range=(1, 5),
            probe_frame=5,
        )


def test_stitch_clips_strict_with_missing_files_raises(tmp_path):
    template = str(tmp_path / "missing.{frame:04d}.usda")
    with pytest.raises(FileNotFoundError):
        stitch_clips(
            filepath_template=template,
            primpath="/World/Sim",
            output_path=str(tmp_path / "x.usda"),
            frame_range=(1, 3),
            strict=True,
        )


def test_stitch_clips_default_probe_missing_file_raises(tmp_path):
    """Even with strict=False, the default-probe-frame branch must validate."""
    template = str(tmp_path / "missing.{frame:04d}.usda")
    with pytest.raises(FileNotFoundError):
        stitch_clips(
            filepath_template=template,
            primpath="/World/Sim",
            output_path=str(tmp_path / "x.usda"),
            frame_range=(1, 3),
        )


def test_stitch_clips_custom_clip_set(tmp_path, frame_sequence):
    out = str(tmp_path / "stitched.usda")
    stitch_clips(
        filepath_template=frame_sequence,
        primpath="/World/Sim",
        output_path=out,
        frame_range=(1, 3),
        clip_set="simCache",
    )
    stage = Usd.Stage.Open(out)
    root = stage.GetPrimAtPath("/World/Sim")
    clip_api = Usd.ClipsAPI(root)
    asset_paths = clip_api.GetClipAssetPaths("simCache")
    assert len(asset_paths) == 3
