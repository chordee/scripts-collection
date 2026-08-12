"""Tests for chd_toolkits.core USD helpers.

These import ``chd_toolkits.core``, which does a top-level ``import hou`` —
so the whole file is skipped under plain Python and is only collected when
running via ``hython -m pytest`` (or ``python tests/run_hython.py``).
"""

import pytest

# core.py does top-level `import hou`; skip the whole module if hou is unavailable.
pytest.importorskip("hou")
pytest.importorskip("pxr")

from pxr import Sdf, Usd, UsdGeom, UsdShade, UsdVol

from chd_toolkits.core import (
    compute_prim_scale,
    dump_json,
    get_all_asset_paths_from_prim,
    get_all_asset_paths_from_stage,
    get_all_clip_sequences_from_prim,
    get_all_clip_sequences_from_stage,
    get_all_layers_in_layer,
    get_all_shader_texture_paths_from_stage,
    get_all_vdb_paths_from_stage,
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


def test_get_all_asset_paths_from_stage_rejects_relative_prim_path():
    stage = Usd.Stage.CreateInMemory()
    with pytest.raises(ValueError):
        get_all_asset_paths_from_stage(stage, "Looks")


def test_get_all_asset_paths_from_prim_drops_udim_template():
    """Existing (pre-shader-helper) behavior: a <UDIM> templated path has no
    resolvedPath, so it is silently excluded — this must stay true after
    _asset_paths_from_value gains udim_aware/missing_out params, since
    get_all_asset_paths_from_prim never opts into either.
    """
    stage = Usd.Stage.CreateInMemory()
    prim = stage.DefinePrim("/X", "Xform")
    attr = prim.CreateAttribute("myAsset", Sdf.ValueTypeNames.Asset)
    attr.Set(Sdf.AssetPath("textures/diffuse.<UDIM>.exr"))
    assert get_all_asset_paths_from_prim(prim) == []


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


def test_get_all_layers_in_layer_handles_missing_file(tmp_path):
    assert get_all_layers_in_layer(str(tmp_path / "nonexistent.usda")) == []


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
    # Must terminate; b is found; a (the root layer) is not returned.
    assert any("b.usda" in d for d in deps)
    assert not any("a.usda" in d for d in deps)


def test_get_all_layers_in_layer_report_missing_false_returns_plain_list(tmp_path):
    sub_path = str(tmp_path / "sub.usda")
    Usd.Stage.CreateNew(sub_path).Save()
    root_path = str(tmp_path / "root.usda")
    root_stage = Usd.Stage.CreateNew(root_path)
    root_stage.GetRootLayer().subLayerPaths.append("./sub.usda")
    root_stage.Save()

    deps = get_all_layers_in_layer(root_path)
    assert isinstance(deps, list)
    assert any("sub.usda" in d for d in deps)


def test_get_all_layers_in_layer_report_missing_true_flags_broken_sublayer(tmp_path):
    root_path = str(tmp_path / "root.usda")
    root_stage = Usd.Stage.CreateNew(root_path)
    root_stage.GetRootLayer().subLayerPaths.append("./missing.usda")
    root_stage.Save()

    found, missing = get_all_layers_in_layer(root_path, report_missing=True)
    assert any("missing.usda" in d for d in missing)
    # A missing dependency is still reported as "found" (it was referenced),
    # just also flagged as unopenable.
    assert any("missing.usda" in d for d in found)


def test_get_all_layers_in_layer_report_missing_true_no_missing_when_all_resolve(tmp_path):
    sub_path = str(tmp_path / "sub.usda")
    Usd.Stage.CreateNew(sub_path).Save()
    root_path = str(tmp_path / "root.usda")
    root_stage = Usd.Stage.CreateNew(root_path)
    root_stage.GetRootLayer().subLayerPaths.append("./sub.usda")
    root_stage.Save()

    found, missing = get_all_layers_in_layer(root_path, report_missing=True)
    assert any("sub.usda" in d for d in found)
    assert missing == []


# ---------------------------------------------------------------------------
# get_all_shader_texture_paths_from_stage
# ---------------------------------------------------------------------------


def test_get_all_shader_texture_paths_from_stage_finds_standard_texture_input(tmp_path):
    target = tmp_path / "diffuse.exr"
    target.write_text("fake exr")
    stage = Usd.Stage.CreateInMemory()
    shader = UsdShade.Shader.Define(stage, "/Looks/mat/Texture")
    shader.CreateIdAttr("UsdUVTexture")
    shader.CreateInput("file", Sdf.ValueTypeNames.Asset).Set(Sdf.AssetPath(str(target)))

    paths = get_all_shader_texture_paths_from_stage(stage)
    assert len(paths) == 1
    assert paths[0].endswith("diffuse.exr")


def test_get_all_shader_texture_paths_from_stage_finds_custom_named_input(tmp_path):
    target = tmp_path / "normal.exr"
    target.write_text("fake exr")
    stage = Usd.Stage.CreateInMemory()
    shader = UsdShade.Shader.Define(stage, "/Looks/mat/CustomShader")
    shader.CreateInput("normalMap", Sdf.ValueTypeNames.Asset).Set(Sdf.AssetPath(str(target)))

    paths = get_all_shader_texture_paths_from_stage(stage)
    assert len(paths) == 1
    assert paths[0].endswith("normal.exr")


def test_get_all_shader_texture_paths_from_stage_ignores_non_asset_inputs(tmp_path):
    target = tmp_path / "diffuse.exr"
    target.write_text("fake exr")
    stage = Usd.Stage.CreateInMemory()
    shader = UsdShade.Shader.Define(stage, "/Looks/mat/Texture")
    shader.CreateInput("scale", Sdf.ValueTypeNames.Float).Set(2.0)
    shader.CreateInput("file", Sdf.ValueTypeNames.Asset).Set(Sdf.AssetPath(str(target)))

    paths = get_all_shader_texture_paths_from_stage(stage)
    assert len(paths) == 1
    assert paths[0].endswith("diffuse.exr")


def test_get_all_shader_texture_paths_from_stage_ignores_non_shader_prims(tmp_path):
    target = tmp_path / "diffuse.exr"
    target.write_text("fake exr")
    stage = Usd.Stage.CreateInMemory()
    prim = stage.DefinePrim("/X", "Xform")
    attr = prim.CreateAttribute("notAShaderInput", Sdf.ValueTypeNames.Asset)
    attr.Set(Sdf.AssetPath(str(target)))

    paths = get_all_shader_texture_paths_from_stage(stage)
    assert paths == []


def test_get_all_shader_texture_paths_from_stage_includes_unbound_orphan_shader(tmp_path):
    target = tmp_path / "diffuse.exr"
    target.write_text("fake exr")
    stage = Usd.Stage.CreateInMemory()
    # No MaterialBindingAPI applied anywhere — shader is "orphaned".
    shader = UsdShade.Shader.Define(stage, "/Looks/unused/Texture")
    shader.CreateInput("file", Sdf.ValueTypeNames.Asset).Set(Sdf.AssetPath(str(target)))

    paths = get_all_shader_texture_paths_from_stage(stage)
    assert len(paths) == 1


def test_get_all_shader_texture_paths_from_stage_finds_asset_array_input(tmp_path):
    target1 = tmp_path / "diffuse.exr"
    target2 = tmp_path / "normal.exr"
    target1.write_text("fake exr")
    target2.write_text("fake exr")
    stage = Usd.Stage.CreateInMemory()
    shader = UsdShade.Shader.Define(stage, "/Looks/mat/Texture")
    shader.CreateInput("files", Sdf.ValueTypeNames.AssetArray).Set(
        [Sdf.AssetPath(str(target1)), Sdf.AssetPath(str(target2))]
    )

    paths = get_all_shader_texture_paths_from_stage(stage)
    assert len(paths) == 2
    assert any(p.endswith("diffuse.exr") for p in paths)
    assert any(p.endswith("normal.exr") for p in paths)


def test_get_all_shader_texture_paths_from_stage_finds_time_sampled_input(tmp_path):
    target1 = tmp_path / "frame1.exr"
    target2 = tmp_path / "frame2.exr"
    target1.write_text("fake exr")
    target2.write_text("fake exr")
    stage = Usd.Stage.CreateInMemory()
    shader = UsdShade.Shader.Define(stage, "/Looks/mat/Texture")
    file_input = shader.CreateInput("file", Sdf.ValueTypeNames.Asset)
    file_input.GetAttr().Set(Sdf.AssetPath(str(target1)), 1.0)
    file_input.GetAttr().Set(Sdf.AssetPath(str(target2)), 2.0)

    paths = get_all_shader_texture_paths_from_stage(stage)
    assert len(paths) == 2
    assert any(p.endswith("frame1.exr") for p in paths)
    assert any(p.endswith("frame2.exr") for p in paths)


def test_get_all_shader_texture_paths_from_stage_rejects_relative_prim_path():
    stage = Usd.Stage.CreateInMemory()
    with pytest.raises(ValueError):
        get_all_shader_texture_paths_from_stage(stage, "Looks")


def test_get_all_shader_texture_paths_from_stage_udim_template_in_default_result():
    stage = Usd.Stage.CreateInMemory()
    shader = UsdShade.Shader.Define(stage, "/Looks/mat/Texture")
    shader.CreateInput("file", Sdf.ValueTypeNames.Asset).Set(
        Sdf.AssetPath("textures/diffuse.<UDIM>.exr")
    )

    paths = get_all_shader_texture_paths_from_stage(stage)
    assert any("<UDIM>" in p for p in paths)


def test_get_all_shader_texture_paths_from_stage_udim_not_in_missing():
    stage = Usd.Stage.CreateInMemory()
    shader = UsdShade.Shader.Define(stage, "/Looks/mat/Texture")
    shader.CreateInput("file", Sdf.ValueTypeNames.Asset).Set(
        Sdf.AssetPath("textures/diffuse.<UDIM>.exr")
    )

    found, missing = get_all_shader_texture_paths_from_stage(stage, report_missing=True)
    assert any("<UDIM>" in p for p in found)
    assert missing == []


def test_get_all_shader_texture_paths_from_stage_reports_broken_non_udim_path(tmp_path):
    broken = str(tmp_path / "does_not_exist.exr")
    stage = Usd.Stage.CreateInMemory()
    shader = UsdShade.Shader.Define(stage, "/Looks/mat/Texture")
    shader.CreateInput("file", Sdf.ValueTypeNames.Asset).Set(Sdf.AssetPath(broken))

    found, missing = get_all_shader_texture_paths_from_stage(stage, report_missing=True)
    assert found == []
    assert any("does_not_exist.exr" in m for m in missing)


def test_get_all_shader_texture_paths_from_stage_missing_default_off(tmp_path):
    """When report_missing=False (default), a broken path contributes nothing
    (not resolved, and there's no missing list to inspect) — the return type
    stays a plain list.
    """
    broken = str(tmp_path / "does_not_exist.exr")
    stage = Usd.Stage.CreateInMemory()
    shader = UsdShade.Shader.Define(stage, "/Looks/mat/Texture")
    shader.CreateInput("file", Sdf.ValueTypeNames.Asset).Set(Sdf.AssetPath(broken))

    paths = get_all_shader_texture_paths_from_stage(stage)
    assert paths == []


# ---------------------------------------------------------------------------
# get_all_vdb_paths_from_stage
# ---------------------------------------------------------------------------


def test_get_all_vdb_paths_from_stage_finds_single_time_sample(tmp_path):
    target = tmp_path / "sim.0001.vdb"
    target.write_text("fake vdb")
    stage = Usd.Stage.CreateInMemory()
    vdb = UsdVol.OpenVDBAsset.Define(stage, "/Volume/density")
    vdb.GetFilePathAttr().Set(Sdf.AssetPath(str(target)), 1.0)

    paths = get_all_vdb_paths_from_stage(stage)
    assert len(paths) == 1
    assert paths[0].endswith("sim.0001.vdb")


def test_get_all_vdb_paths_from_stage_unions_multiple_time_samples(tmp_path):
    targets = []
    for frame in (1, 2, 3):
        target = tmp_path / f"sim.{frame:04d}.vdb"
        target.write_text("fake vdb")
        targets.append(target)
    stage = Usd.Stage.CreateInMemory()
    vdb = UsdVol.OpenVDBAsset.Define(stage, "/Volume/density")
    attr = vdb.GetFilePathAttr()
    for frame, target in zip((1, 2, 3), targets):
        attr.Set(Sdf.AssetPath(str(target)), float(frame))

    paths = get_all_vdb_paths_from_stage(stage)
    assert len(paths) == 3
    for target in targets:
        assert any(p.endswith(target.name) for p in paths)


def test_get_all_vdb_paths_from_stage_falls_back_to_default_value(tmp_path):
    target = tmp_path / "static.vdb"
    target.write_text("fake vdb")
    stage = Usd.Stage.CreateInMemory()
    vdb = UsdVol.OpenVDBAsset.Define(stage, "/Volume/density")
    vdb.GetFilePathAttr().Set(Sdf.AssetPath(str(target)))  # no time code -> default value

    paths = get_all_vdb_paths_from_stage(stage)
    assert len(paths) == 1
    assert paths[0].endswith("static.vdb")


def test_get_all_vdb_paths_from_stage_ignores_field3d_asset(tmp_path):
    target = tmp_path / "sim.f3d"
    target.write_text("fake field3d")
    stage = Usd.Stage.CreateInMemory()
    field3d = UsdVol.Field3DAsset.Define(stage, "/Volume/density")
    field3d.GetFilePathAttr().Set(Sdf.AssetPath(str(target)), 1.0)

    paths = get_all_vdb_paths_from_stage(stage)
    assert paths == []


def test_get_all_vdb_paths_from_stage_ignores_unrelated_prims(tmp_path):
    target = tmp_path / "sim.vdb"
    target.write_text("fake vdb")
    stage = Usd.Stage.CreateInMemory()
    prim = stage.DefinePrim("/X", "Xform")
    attr = prim.CreateAttribute("notAVdbFilePath", Sdf.ValueTypeNames.Asset)
    attr.Set(Sdf.AssetPath(str(target)))

    paths = get_all_vdb_paths_from_stage(stage)
    assert paths == []


def test_get_all_vdb_paths_from_stage_rejects_relative_prim_path():
    stage = Usd.Stage.CreateInMemory()
    with pytest.raises(ValueError):
        get_all_vdb_paths_from_stage(stage, "Volume")


def test_get_all_vdb_paths_from_stage_report_missing_separates_found_and_missing(tmp_path):
    resolvable = tmp_path / "sim.0001.vdb"
    resolvable.write_text("fake vdb")
    broken = str(tmp_path / "does_not_exist.vdb")

    stage = Usd.Stage.CreateInMemory()
    vdb = UsdVol.OpenVDBAsset.Define(stage, "/Volume/density")
    attr = vdb.GetFilePathAttr()
    attr.Set(Sdf.AssetPath(str(resolvable)), 1.0)
    attr.Set(Sdf.AssetPath(broken), 2.0)

    found, missing = get_all_vdb_paths_from_stage(stage, report_missing=True)
    assert any(p.endswith("sim.0001.vdb") for p in found)
    assert not any("does_not_exist.vdb" in p for p in found)
    assert any("does_not_exist.vdb" in m for m in missing)


def test_get_all_vdb_paths_from_stage_missing_default_off(tmp_path):
    broken = str(tmp_path / "does_not_exist.vdb")
    stage = Usd.Stage.CreateInMemory()
    vdb = UsdVol.OpenVDBAsset.Define(stage, "/Volume/density")
    vdb.GetFilePathAttr().Set(Sdf.AssetPath(broken), 1.0)

    paths = get_all_vdb_paths_from_stage(stage)
    assert paths == []


# ---------------------------------------------------------------------------
# get_all_clip_sequences_from_stage: prim_path validation
# ---------------------------------------------------------------------------


def test_get_all_clip_sequences_from_stage_rejects_relative_prim_path():
    stage = Usd.Stage.CreateInMemory()
    with pytest.raises(ValueError):
        get_all_clip_sequences_from_stage(stage, "Scope")


def test_get_all_clip_sequences_from_stage_accepts_sdf_path(tmp_path):
    dummy = tmp_path / "dummy.usda"
    dummy.write_text("#usda 1.0\n")
    stage = Usd.Stage.CreateInMemory()
    prim = stage.DefinePrim("/Scope", "Xform")
    Usd.ClipsAPI(prim).SetClipAssetPaths([Sdf.AssetPath(str(dummy))], "default")

    paths = get_all_clip_sequences_from_stage(stage, Sdf.Path("/Scope"))
    assert len(paths) == 1


# ---------------------------------------------------------------------------
# dump_json
# ---------------------------------------------------------------------------


def test_dump_json_returns_string_without_path():
    result = dump_json(["a.usda", "b.usda"])
    assert isinstance(result, str)
    assert "a.usda" in result


def test_dump_json_writes_file_and_returns_none(tmp_path):
    out_path = tmp_path / "deps.json"
    result = dump_json({"found": ["a.usda"], "missing": []}, out_path)
    assert result is None
    assert out_path.exists()
    assert "a.usda" in out_path.read_text(encoding="utf-8")
