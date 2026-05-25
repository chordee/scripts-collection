"""Tests for chd_toolkits.core USD helpers.

These import ``chd_toolkits.core``, which does a top-level ``import hou`` —
so the whole file is skipped under plain Python and is only collected when
running via ``hython -m pytest`` (or ``python tests/run_hython.py``).
"""

import pytest

# core.py does top-level `import hou`; skip the whole module if hou is unavailable.
pytest.importorskip("hou")
pytest.importorskip("pxr")

from pxr import Sdf, Usd, UsdGeom, UsdShade

from chd_toolkits.core import (
    compute_prim_scale,
    get_all_asset_paths_from_prim,
    get_all_asset_paths_from_stage,
    get_all_clip_sequences_from_prim,
    get_all_clip_sequences_from_stage,
    get_all_layers_in_layer,
    get_clip_names,
    get_clip_sequences_from_prim,
    get_material_from_prim,
)


# ---------------------------------------------------------------------------
# compute_prim_scale
# ---------------------------------------------------------------------------


def test_compute_prim_scale_identity():
    stage = Usd.Stage.CreateInMemory()
    xform = UsdGeom.Xform.Define(stage, "/X")
    scale = compute_prim_scale(xform.GetPrim())
    assert scale == pytest.approx([1.0, 1.0, 1.0])


def test_compute_prim_scale_non_uniform():
    stage = Usd.Stage.CreateInMemory()
    xform = UsdGeom.Xform.Define(stage, "/X")
    xform.AddScaleOp().Set((2.0, 3.0, 4.0))
    scale = compute_prim_scale(xform.GetPrim())
    assert scale[0] == pytest.approx(2.0)
    assert scale[1] == pytest.approx(3.0)
    assert scale[2] == pytest.approx(4.0)


def test_compute_prim_scale_inherits_parent():
    stage = Usd.Stage.CreateInMemory()
    parent = UsdGeom.Xform.Define(stage, "/P")
    parent.AddScaleOp().Set((2.0, 2.0, 2.0))
    child = UsdGeom.Xform.Define(stage, "/P/C")
    scale = compute_prim_scale(child.GetPrim())
    assert scale[0] == pytest.approx(2.0)


# ---------------------------------------------------------------------------
# get_material_from_prim
# ---------------------------------------------------------------------------


def test_get_material_from_prim_no_binding():
    stage = Usd.Stage.CreateInMemory()
    prim = UsdGeom.Xform.Define(stage, "/X").GetPrim()
    assert get_material_from_prim(prim) is None


def test_get_material_from_prim_with_direct_binding():
    stage = Usd.Stage.CreateInMemory()
    geom = UsdGeom.Xform.Define(stage, "/Geo").GetPrim()
    mat = UsdShade.Material.Define(stage, "/Mat")
    UsdShade.MaterialBindingAPI.Apply(geom).Bind(mat)
    result = get_material_from_prim(geom)
    assert result is not None
    assert result.GetPath() == mat.GetPath()


# ---------------------------------------------------------------------------
# get_all_asset_paths_from_prim / _from_stage
# ---------------------------------------------------------------------------


def test_get_all_asset_paths_from_prim_empty():
    stage = Usd.Stage.CreateInMemory()
    prim = stage.DefinePrim("/X", "Xform")
    assert get_all_asset_paths_from_prim(prim) == []


def test_get_all_asset_paths_from_prim_single_asset_attr(tmp_path):
    target = tmp_path / "ref.usda"
    target.write_text("#usda 1.0\n")  # so resolvedPath != ""
    stage = Usd.Stage.CreateInMemory()
    prim = stage.DefinePrim("/X", "Xform")
    attr = prim.CreateAttribute("myAsset", Sdf.ValueTypeNames.Asset)
    attr.Set(Sdf.AssetPath(str(target)))
    paths = get_all_asset_paths_from_prim(prim)
    assert len(paths) == 1
    assert paths[0].endswith("ref.usda")


def test_get_all_asset_paths_from_prim_asset_array(tmp_path):
    target1 = tmp_path / "a.usda"
    target2 = tmp_path / "b.usda"
    target1.write_text("#usda 1.0\n")
    target2.write_text("#usda 1.0\n")
    stage = Usd.Stage.CreateInMemory()
    prim = stage.DefinePrim("/X", "Xform")
    attr = prim.CreateAttribute("myAssets", Sdf.ValueTypeNames.AssetArray)
    attr.Set([Sdf.AssetPath(str(target1)), Sdf.AssetPath(str(target2))])
    paths = get_all_asset_paths_from_prim(prim)
    assert len(paths) == 2


def test_get_all_asset_paths_from_stage_walks_children(tmp_path):
    target = tmp_path / "shared.usda"
    target.write_text("#usda 1.0\n")
    stage = Usd.Stage.CreateInMemory()
    for path in ("/A", "/B", "/B/C"):
        prim = stage.DefinePrim(path, "Xform")
        attr = prim.CreateAttribute("asset", Sdf.ValueTypeNames.Asset)
        attr.Set(Sdf.AssetPath(str(target)))
    paths = get_all_asset_paths_from_stage(stage)
    # Deduped: only one unique resolvedPath
    assert len(paths) == 1


# ---------------------------------------------------------------------------
# get_clip_names / get_clip_sequences_from_prim
# ---------------------------------------------------------------------------


def test_get_clip_names_none_when_no_metadata():
    stage = Usd.Stage.CreateInMemory()
    prim = stage.DefinePrim("/X", "Xform")
    assert get_clip_names(prim) is None


def test_get_clip_names_lists_clipsets(tmp_path):
    dummy = tmp_path / "dummy.usda"
    dummy.write_text("#usda 1.0\n")
    stage = Usd.Stage.CreateInMemory()
    prim = stage.DefinePrim("/X", "Xform")
    clip_api = Usd.ClipsAPI(prim)
    clip_api.SetClipAssetPaths([Sdf.AssetPath(str(dummy))], "myClip")
    names = get_clip_names(prim)
    assert names is not None
    assert "myClip" in names


def test_get_clip_sequences_from_prim_returns_paths(tmp_path):
    a = tmp_path / "a.usda"
    b = tmp_path / "b.usda"
    a.write_text("#usda 1.0\n")
    b.write_text("#usda 1.0\n")
    stage = Usd.Stage.CreateInMemory()
    prim = stage.DefinePrim("/X", "Xform")
    clip_api = Usd.ClipsAPI(prim)
    clip_api.SetClipAssetPaths(
        [Sdf.AssetPath(str(a)), Sdf.AssetPath(str(b))], "default"
    )
    paths = get_clip_sequences_from_prim(prim)
    assert paths is not None
    assert len(paths) == 2


def test_get_clip_sequences_from_prim_none_when_no_metadata():
    stage = Usd.Stage.CreateInMemory()
    prim = stage.DefinePrim("/X", "Xform")
    assert get_clip_sequences_from_prim(prim) is None


def test_get_all_clip_sequences_from_prim_unions_clipsets(tmp_path):
    a = tmp_path / "a.usda"
    b = tmp_path / "b.usda"
    a.write_text("#usda 1.0\n")
    b.write_text("#usda 1.0\n")
    stage = Usd.Stage.CreateInMemory()
    prim = stage.DefinePrim("/X", "Xform")
    clip_api = Usd.ClipsAPI(prim)
    clip_api.SetClipAssetPaths([Sdf.AssetPath(str(a))], "clipA")
    clip_api.SetClipAssetPaths([Sdf.AssetPath(str(b))], "clipB")
    paths = get_all_clip_sequences_from_prim(prim)
    assert paths is not None
    assert len(paths) == 2


def test_get_all_clip_sequences_from_stage_finds_clip_prims(tmp_path):
    dummy = tmp_path / "dummy.usda"
    dummy.write_text("#usda 1.0\n")
    stage = Usd.Stage.CreateInMemory()
    for path in ("/A", "/B"):
        prim = stage.DefinePrim(path, "Xform")
        Usd.ClipsAPI(prim).SetClipAssetPaths(
            [Sdf.AssetPath(str(dummy))], "default"
        )
    paths = get_all_clip_sequences_from_stage(stage)
    assert len(paths) == 1  # deduped


# ---------------------------------------------------------------------------
# get_all_layers_in_layer
# ---------------------------------------------------------------------------


def test_get_all_layers_in_layer_no_dependencies(tmp_path):
    root = str(tmp_path / "root.usda")
    Usd.Stage.CreateNew(root).Save()
    assert get_all_layers_in_layer(root) == []


def test_get_all_layers_in_layer_with_sublayer(tmp_path):
    sub_path = str(tmp_path / "sub.usda")
    Usd.Stage.CreateNew(sub_path).Save()

    root_path = str(tmp_path / "root.usda")
    root_stage = Usd.Stage.CreateNew(root_path)
    root_stage.GetRootLayer().subLayerPaths.append("./sub.usda")
    root_stage.Save()

    deps = get_all_layers_in_layer(root_path)
    assert any("sub.usda" in d for d in deps)


def test_get_all_layers_in_layer_handles_missing_file():
    assert get_all_layers_in_layer("/nonexistent/path.usda") == []


def test_get_all_layers_in_layer_handles_cycle(tmp_path):
    """Two layers sublayer-ing each other must not cause infinite recursion."""
    a_path = str(tmp_path / "a.usda")
    b_path = str(tmp_path / "b.usda")
    # Create both first so FindOrOpen succeeds
    Usd.Stage.CreateNew(a_path).Save()
    Usd.Stage.CreateNew(b_path).Save()
    # Then wire the cycle
    layer_a = Sdf.Layer.FindOrOpen(a_path)
    layer_b = Sdf.Layer.FindOrOpen(b_path)
    layer_a.subLayerPaths.append("./b.usda")
    layer_b.subLayerPaths.append("./a.usda")
    # SdfLayer.Save in this Houdini USD binding requires the `force` arg explicitly.
    layer_a.Save(False)
    layer_b.Save(False)

    deps = get_all_layers_in_layer(a_path)
    # Must terminate; b is found, a (the root) is not in the list
    assert any("b.usda" in d for d in deps)
