"""Tests for utils.character_usd_split.

Pure ``pxr`` — no Maya session required. Run under hython or any Python
with ``pxr`` (``pip install usd-core``) available.
"""

import os

import pytest

pytest.importorskip("pxr")

from pxr import Gf, Sdf, Usd, UsdGeom, UsdSkel, Vt

from utils.character_usd_split import (
    _discover_bindings,
    _write_anim_layer,
    _write_geo_layer,
    _write_skel_layer,
    split_character_usd,
)


def _build_character_stage(
    path,
    with_blendshape=True,
    skel_root_path="/Character",
    default_prim_path=None,
    apply_binding_on_skel_root=False,
    anim_sibling_of_skeleton=False,
):
    """A SkelRoot > Xform "Geom" > Mesh "box" (skinned) + Skeleton + Animation,
    with explicitly-typed intermediate prims (untyped ancestors break
    UsdSkel.Cache discovery — see the plan's Global Constraints).

    ``skel_root_path``/``default_prim_path`` let callers exercise a SkelRoot
    nested below the stage's actual defaultPrim (Finding 1); by default the
    defaultPrim is the SkelRoot itself, matching the original fixture shape.
    ``apply_binding_on_skel_root`` additionally applies SkelBindingAPI to
    the SkelRoot prim itself (Finding 2). ``anim_sibling_of_skeleton`` places
    the Animation prim as a sibling of the Skeleton instead of nested under
    it (Finding 5).
    """
    default_prim_path = default_prim_path or skel_root_path
    stage = Usd.Stage.CreateNew(path)
    if default_prim_path != skel_root_path:
        UsdGeom.Xform.Define(stage, default_prim_path)
    UsdSkel.Root.Define(stage, skel_root_path)
    UsdGeom.Xform.Define(stage, f"{skel_root_path}/Geom")
    mesh = UsdGeom.Mesh.Define(stage, f"{skel_root_path}/Geom/box")
    mesh.CreatePointsAttr(Vt.Vec3fArray([(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)]))
    mesh.CreateFaceVertexCountsAttr(Vt.IntArray([4]))
    mesh.CreateFaceVertexIndicesAttr(Vt.IntArray([0, 1, 2, 3]))

    skel = UsdSkel.Skeleton.Define(stage, f"{skel_root_path}/Skel")
    skel.CreateJointsAttr(Vt.TokenArray(["root", "root/child"]))
    skel.CreateBindTransformsAttr(Vt.Matrix4dArray([Gf.Matrix4d(1), Gf.Matrix4d(1)]))
    skel.CreateRestTransformsAttr(Vt.Matrix4dArray([Gf.Matrix4d(1), Gf.Matrix4d(1)]))

    anim_path = f"{skel_root_path}/Anim" if anim_sibling_of_skeleton else f"{skel_root_path}/Skel/Anim"
    anim = UsdSkel.Animation.Define(stage, anim_path)
    anim.CreateJointsAttr(Vt.TokenArray(["root", "root/child"]))
    trans_attr = anim.CreateTranslationsAttr()
    trans_attr.Set(Vt.Vec3fArray([(0, 0, 0), (0, 1, 0)]), 1.0)
    trans_attr.Set(Vt.Vec3fArray([(0, 0, 0), (0, 2, 0)]), 2.0)
    anim.CreateRotationsAttr().Set(Vt.QuatfArray([Gf.Quatf(1), Gf.Quatf(1)]), 1.0)
    anim.CreateScalesAttr().Set(Vt.Vec3hArray([(1, 1, 1), (1, 1, 1)]), 1.0)

    binding = UsdSkel.BindingAPI.Apply(mesh.GetPrim())
    binding.CreateJointIndicesPrimvar(False, 1).Set(Vt.IntArray([0, 0, 0, 0]))
    binding.CreateJointWeightsPrimvar(False, 1).Set(Vt.FloatArray([1.0] * 4))
    binding.CreateGeomBindTransformAttr().Set(Gf.Matrix4d(1))
    binding.CreateSkeletonRel().SetTargets([skel.GetPath()])

    if with_blendshape:
        bs = UsdSkel.BlendShape.Define(stage, f"{skel_root_path}/Geom/box/blink")
        bs.CreateOffsetsAttr(Vt.Vec3fArray([(0, 0, 0.1)] * 4))
        binding.CreateBlendShapesAttr(Vt.TokenArray(["blink"]))
        binding.CreateBlendShapeTargetsRel().SetTargets([bs.GetPath()])
        anim.CreateBlendShapesAttr(Vt.TokenArray(["blink"]))
        weights_attr = anim.CreateBlendShapeWeightsAttr()
        weights_attr.Set(Vt.FloatArray([0.0]), 1.0)
        weights_attr.Set(Vt.FloatArray([1.0]), 2.0)

    skel_binding = UsdSkel.BindingAPI.Apply(skel.GetPrim())
    skel_binding.CreateAnimationSourceRel().SetTargets([anim.GetPath()])

    if apply_binding_on_skel_root:
        root_binding = UsdSkel.BindingAPI.Apply(stage.GetPrimAtPath(skel_root_path))
        root_binding.CreateSkeletonRel().SetTargets([skel.GetPath()])
        root_binding.CreateAnimationSourceRel().SetTargets([anim.GetPath()])

    stage.SetDefaultPrim(stage.GetPrimAtPath(default_prim_path))
    stage.GetRootLayer().Save()
    return stage


def test_discover_bindings_finds_skeleton_mesh_anim_and_blendshape(tmp_path):
    stage = _build_character_stage(str(tmp_path / "character.usda"))

    bindings = _discover_bindings(stage)

    assert len(bindings) == 1
    binding = bindings[0]
    assert binding.skeleton_path == Sdf.Path("/Character/Skel")
    assert binding.anim_path == Sdf.Path("/Character/Skel/Anim")
    assert binding.skinned_mesh_paths == [Sdf.Path("/Character/Geom/box")]
    assert binding.blend_shape_paths == [Sdf.Path("/Character/Geom/box/blink")]


def test_discover_bindings_no_blendshape_target(tmp_path):
    stage = _build_character_stage(str(tmp_path / "character.usda"), with_blendshape=False)

    bindings = _discover_bindings(stage)

    assert len(bindings) == 1
    assert bindings[0].blend_shape_paths == []


def test_discover_bindings_returns_empty_for_stage_without_skinning(tmp_path):
    path = str(tmp_path / "plain.usda")
    stage = Usd.Stage.CreateNew(path)
    UsdGeom.Mesh.Define(stage, "/Plain")
    stage.GetRootLayer().Save()

    assert _discover_bindings(stage) == []


def test_write_geo_layer_strips_skeleton_content(tmp_path):
    stage = _build_character_stage(str(tmp_path / "character.usda"))
    geo_path = str(tmp_path / "character_geo.usd")

    _write_geo_layer(stage, geo_path)

    geo_stage = Usd.Stage.Open(geo_path)
    mesh_prim = geo_stage.GetPrimAtPath("/Character/Geom/box")
    assert mesh_prim.IsValid()
    assert list(UsdGeom.Mesh(mesh_prim).GetPointsAttr().Get()) == [
        Gf.Vec3f(0, 0, 0), Gf.Vec3f(1, 0, 0), Gf.Vec3f(1, 1, 0), Gf.Vec3f(0, 1, 0),
    ]
    assert mesh_prim.GetAppliedSchemas() == []
    assert not any(p.startswith("skel:") or p.startswith("primvars:skel:") for p in mesh_prim.GetPropertyNames())
    assert not geo_stage.GetPrimAtPath("/Character/Skel").IsValid()
    assert not geo_stage.GetPrimAtPath("/Character/Skel/Anim").IsValid()
    assert not geo_stage.GetPrimAtPath("/Character/Geom/box/blink").IsValid()


def test_write_geo_layer_no_blendshape(tmp_path):
    stage = _build_character_stage(str(tmp_path / "character.usda"), with_blendshape=False)
    geo_path = str(tmp_path / "character_geo.usd")

    _write_geo_layer(stage, geo_path)

    geo_stage = Usd.Stage.Open(geo_path)
    assert geo_stage.GetPrimAtPath("/Character/Geom/box").IsValid()


def test_write_skel_layer_references_geo_and_overlays_skinning(tmp_path):
    stage = _build_character_stage(str(tmp_path / "character.usda"))
    bindings = _discover_bindings(stage)
    geo_path = str(tmp_path / "character_geo.usd")
    skel_path = str(tmp_path / "character_skel.usd")
    _write_geo_layer(stage, geo_path)

    _write_skel_layer(stage, bindings, geo_path, skel_path)

    skel_stage = Usd.Stage.Open(skel_path)
    mesh_prim = skel_stage.GetPrimAtPath("/Character/Geom/box")

    # Points come from the reference to geo.usd -- not duplicated locally.
    assert list(UsdGeom.Mesh(mesh_prim).GetPointsAttr().Get()) == [
        Gf.Vec3f(0, 0, 0), Gf.Vec3f(1, 0, 0), Gf.Vec3f(1, 1, 0), Gf.Vec3f(0, 1, 0),
    ]

    mesh_binding = UsdSkel.BindingAPI(mesh_prim)
    assert list(mesh_binding.GetJointIndicesPrimvar().Get()) == [0, 0, 0, 0]
    assert list(mesh_binding.GetJointWeightsPrimvar().Get()) == [1.0, 1.0, 1.0, 1.0]
    assert mesh_binding.GetGeomBindTransformAttr().Get() == Gf.Matrix4d(1)
    assert mesh_binding.GetSkeletonRel().GetTargets() == [Sdf.Path("/Character/Skel")]
    assert mesh_binding.GetBlendShapesAttr().Get() == ["blink"]
    assert mesh_binding.GetBlendShapeTargetsRel().GetTargets() == [Sdf.Path("/Character/Geom/box/blink")]

    skel_prim = skel_stage.GetPrimAtPath("/Character/Skel")
    assert list(UsdSkel.Skeleton(skel_prim).GetJointsAttr().Get()) == ["root", "root/child"]
    assert UsdSkel.BindingAPI(skel_prim).GetAnimationSourceRel().GetTargets() == []

    # The Anim prim must NOT leak into skel.usd -- it belongs only in anim.usd.
    assert not skel_stage.GetPrimAtPath("/Character/Skel/Anim").IsValid()

    blink_prim = skel_stage.GetPrimAtPath("/Character/Geom/box/blink")
    assert blink_prim.IsValid()
    assert list(UsdSkel.BlendShape(blink_prim).GetOffsetsAttr().Get()) == [Gf.Vec3f(0, 0, 0.1)] * 4


def test_write_skel_layer_no_blendshape(tmp_path):
    stage = _build_character_stage(str(tmp_path / "character.usda"), with_blendshape=False)
    bindings = _discover_bindings(stage)
    geo_path = str(tmp_path / "character_geo.usd")
    skel_path = str(tmp_path / "character_skel.usd")
    _write_geo_layer(stage, geo_path)

    _write_skel_layer(stage, bindings, geo_path, skel_path)

    skel_stage = Usd.Stage.Open(skel_path)
    mesh_binding = UsdSkel.BindingAPI(skel_stage.GetPrimAtPath("/Character/Geom/box"))
    assert mesh_binding.GetBlendShapesAttr().Get() is None
    assert not skel_stage.GetPrimAtPath("/Character/Geom/box/blink").IsValid()


def test_write_anim_layer_is_standalone_with_correct_time_samples(tmp_path):
    stage = _build_character_stage(str(tmp_path / "character.usda"))
    bindings = _discover_bindings(stage)
    anim_path = str(tmp_path / "character_anim.usd")

    _write_anim_layer(stage, bindings, anim_path)

    anim_stage = Usd.Stage.Open(anim_path)
    assert list(anim_stage.GetRootLayer().subLayerPaths) == []

    anim_prim = anim_stage.GetPrimAtPath("/Character/Skel/Anim")
    assert anim_prim.IsValid()
    anim_schema = UsdSkel.Animation(anim_prim)
    assert anim_schema.GetTranslationsAttr().GetTimeSamples() == [1.0, 2.0]
    assert list(anim_schema.GetTranslationsAttr().Get(2.0)) == [Gf.Vec3f(0, 0, 0), Gf.Vec3f(0, 2, 0)]
    assert anim_schema.GetBlendShapeWeightsAttr().GetTimeSamples() == [1.0, 2.0]
    assert list(anim_schema.GetBlendShapeWeightsAttr().Get(2.0)) == [1.0]


def test_split_character_usd_end_to_end(tmp_path):
    src_path = str(tmp_path / "character.usda")
    _build_character_stage(src_path)

    geo_path, skel_path, anim_path = split_character_usd(src_path)

    assert geo_path == str(tmp_path / "character_geo.usd")
    assert skel_path == str(tmp_path / "character_skel.usd")
    assert anim_path == str(tmp_path / "character_anim.usd")
    assert os.path.exists(geo_path)
    assert os.path.exists(skel_path)
    assert os.path.exists(anim_path)

    # Spot-check the composed skel.usd actually resolves geometry + skinning together.
    skel_stage = Usd.Stage.Open(skel_path)
    mesh_prim = skel_stage.GetPrimAtPath("/Character/Geom/box")
    assert list(UsdGeom.Mesh(mesh_prim).GetPointsAttr().Get()) == [
        Gf.Vec3f(0, 0, 0), Gf.Vec3f(1, 0, 0), Gf.Vec3f(1, 1, 0), Gf.Vec3f(0, 1, 0),
    ]
    assert list(UsdSkel.BindingAPI(mesh_prim).GetJointIndicesPrimvar().Get()) == [0, 0, 0, 0]


def test_split_character_usd_custom_output_dir(tmp_path):
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    src_path = str(src_dir / "character.usda")
    _build_character_stage(src_path)

    geo_path, skel_path, anim_path = split_character_usd(src_path, output_dir=str(out_dir))

    assert os.path.dirname(geo_path) == str(out_dir)
    assert os.path.dirname(skel_path) == str(out_dir)
    assert os.path.dirname(anim_path) == str(out_dir)
    assert os.path.exists(geo_path)
    assert os.path.exists(skel_path)
    assert os.path.exists(anim_path)


def test_split_character_usd_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        split_character_usd(str(tmp_path / "nope.usd"))


def test_split_character_usd_no_skel_binding_raises(tmp_path):
    path = str(tmp_path / "plain.usda")
    stage = Usd.Stage.CreateNew(path)
    UsdGeom.Mesh.Define(stage, "/Plain")
    stage.GetRootLayer().Save()

    with pytest.raises(ValueError):
        split_character_usd(path)


def test_split_character_usd_no_default_prim_raises(tmp_path):
    path = str(tmp_path / "character.usda")
    stage = _build_character_stage(path)
    stage.ClearDefaultPrim()
    stage.GetRootLayer().Save()

    with pytest.raises(ValueError):
        split_character_usd(path)


def test_split_character_usd_cleans_up_partial_output_on_failure(tmp_path, monkeypatch):
    import utils.character_usd_split as split_mod

    path = str(tmp_path / "character.usda")
    _build_character_stage(path)

    def _boom(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(split_mod, "_write_skel_layer", _boom)

    with pytest.raises(RuntimeError):
        split_character_usd(path)

    assert not os.path.exists(str(tmp_path / "character_geo.usd"))
    assert not os.path.exists(str(tmp_path / "character_skel.usd"))
    assert not os.path.exists(str(tmp_path / "character_anim.usd"))


def test_write_anim_layer_copies_stage_time_metadata(tmp_path):
    path = str(tmp_path / "character.usda")
    stage = _build_character_stage(path)
    stage.SetStartTimeCode(5)
    stage.SetEndTimeCode(48)
    stage.SetFramesPerSecond(30)
    stage.SetTimeCodesPerSecond(30)
    stage.GetRootLayer().Save()
    bindings = _discover_bindings(stage)
    anim_path = str(tmp_path / "character_anim.usd")

    _write_anim_layer(stage, bindings, anim_path)

    anim_stage = Usd.Stage.Open(anim_path)
    assert anim_stage.GetStartTimeCode() == 5
    assert anim_stage.GetEndTimeCode() == 48
    assert anim_stage.GetFramesPerSecond() == 30
    assert anim_stage.GetTimeCodesPerSecond() == 30


def test_write_anim_layer_does_not_author_metadata_when_unauthored_on_source(tmp_path):
    path = str(tmp_path / "character.usda")
    stage = _build_character_stage(path)
    bindings = _discover_bindings(stage)
    anim_path = str(tmp_path / "character_anim.usd")

    _write_anim_layer(stage, bindings, anim_path)

    anim_stage = Usd.Stage.Open(anim_path)
    assert not anim_stage.HasAuthoredMetadata("startTimeCode")
    assert not anim_stage.HasAuthoredMetadata("endTimeCode")


def test_write_skel_layer_copies_stage_up_axis_and_units(tmp_path):
    path = str(tmp_path / "character.usda")
    stage = _build_character_stage(path)
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    UsdGeom.SetStageMetersPerUnit(stage, 1.0)
    stage.GetRootLayer().Save()
    bindings = _discover_bindings(stage)
    geo_path = str(tmp_path / "character_geo.usd")
    skel_path = str(tmp_path / "character_skel.usd")
    _write_geo_layer(stage, geo_path)

    _write_skel_layer(stage, bindings, geo_path, skel_path)

    skel_stage = Usd.Stage.Open(skel_path)
    assert UsdGeom.GetStageUpAxis(skel_stage) == UsdGeom.Tokens.z
    assert UsdGeom.GetStageMetersPerUnit(skel_stage) == 1.0


def test_split_character_usd_skeleton_nested_two_levels_below_default_prim(tmp_path):
    """Finding 1: SkelRoot/Skeleton nested below the stage's actual defaultPrim
    used to crash _write_skel_layer's Sdf.CopySpec with a nonexistent-ancestor error.
    """
    path = str(tmp_path / "character.usda")
    _build_character_stage(path, default_prim_path="/root", skel_root_path="/root/Character")

    geo_path, skel_path, anim_path = split_character_usd(path)

    skel_stage = Usd.Stage.Open(skel_path)
    skel_prim = skel_stage.GetPrimAtPath("/root/Character/Skel")
    assert skel_prim.IsValid()
    assert list(UsdSkel.Skeleton(skel_prim).GetJointsAttr().Get()) == ["root", "root/child"]

    mesh_prim = skel_stage.GetPrimAtPath("/root/Character/Geom/box")
    assert list(UsdGeom.Mesh(mesh_prim).GetPointsAttr().Get()) == [
        Gf.Vec3f(0, 0, 0), Gf.Vec3f(1, 0, 0), Gf.Vec3f(1, 1, 0), Gf.Vec3f(0, 1, 0),
    ]
    assert list(UsdSkel.BindingAPI(mesh_prim).GetJointIndicesPrimvar().Get()) == [0, 0, 0, 0]


def test_write_geo_layer_strips_skel_binding_api_applied_on_skel_root(tmp_path):
    """Finding 2: SkelBindingAPI applied on the SkelRoot (not just the mesh)
    used to leak the schema and a dangling skel:animationSource into geo.usd.
    """
    stage = _build_character_stage(str(tmp_path / "character.usda"), apply_binding_on_skel_root=True)
    geo_path = str(tmp_path / "character_geo.usd")

    _write_geo_layer(stage, geo_path)

    geo_stage = Usd.Stage.Open(geo_path)
    for prim in geo_stage.Traverse():
        assert "SkelBindingAPI" not in prim.GetAppliedSchemas()
        assert not any(
            p.startswith("skel:") or p.startswith("primvars:skel:") for p in prim.GetPropertyNames()
        )


def test_split_character_usd_no_dangling_animation_source_from_skel_root_binding(tmp_path):
    """Finding 2 (end-to-end): a SkelBindingAPI on the SkelRoot must not
    compose a dangling skel:animationSource into skel.usd via the geo.usd reference.
    """
    path = str(tmp_path / "character.usda")
    _build_character_stage(path, apply_binding_on_skel_root=True)

    geo_path, skel_path, anim_path = split_character_usd(path)

    skel_stage = Usd.Stage.Open(skel_path)
    character_prim = skel_stage.GetPrimAtPath("/Character")
    assert "SkelBindingAPI" not in character_prim.GetAppliedSchemas()
    assert UsdSkel.BindingAPI(character_prim).GetAnimationSourceRel().GetTargets() == []


def test_write_geo_layer_removes_sibling_animation_prim(tmp_path):
    """Finding 5: an Animation prim that is a sibling of the Skeleton (not
    nested under it) must still be removed from geo.usd, along with its time samples.
    """
    stage = _build_character_stage(str(tmp_path / "character.usda"), anim_sibling_of_skeleton=True)
    geo_path = str(tmp_path / "character_geo.usd")

    _write_geo_layer(stage, geo_path)

    geo_stage = Usd.Stage.Open(geo_path)
    assert not geo_stage.GetPrimAtPath("/Character/Anim").IsValid()


def test_split_character_usd_sibling_animation_end_to_end(tmp_path):
    path = str(tmp_path / "character.usda")
    _build_character_stage(path, anim_sibling_of_skeleton=True)

    geo_path, skel_path, anim_path = split_character_usd(path)

    geo_stage = Usd.Stage.Open(geo_path)
    assert not geo_stage.GetPrimAtPath("/Character/Anim").IsValid()

    anim_stage = Usd.Stage.Open(anim_path)
    anim_prim = anim_stage.GetPrimAtPath("/Character/Anim")
    assert anim_prim.IsValid()
    assert UsdSkel.Animation(anim_prim).GetTranslationsAttr().GetTimeSamples() == [1.0, 2.0]


def _add_unbound_skeleton(stage, path="/Character/UnboundRig"):
    """A Skeleton+Animation pair with no skinning binding to any mesh --
    matches real mayaUSDExport output for Maya FK/IK control-rig joints,
    which get their own Skeleton+Animation prim even though they never
    drive a mesh's skin weights.
    """
    skel = UsdSkel.Skeleton.Define(stage, path)
    skel.CreateJointsAttr(Vt.TokenArray(["ctrl"]))
    anim = UsdSkel.Animation.Define(stage, f"{path}/Animation")
    anim.CreateJointsAttr(Vt.TokenArray(["ctrl"]))
    anim.CreateTranslationsAttr().Set(Vt.Vec3fArray([(0, 0, 0)]), 1.0)
    UsdSkel.BindingAPI.Apply(skel.GetPrim()).CreateAnimationSourceRel().SetTargets([anim.GetPath()])
    return skel, anim


def test_write_geo_layer_removes_unbound_skeleton_and_animation(tmp_path):
    stage = _build_character_stage(str(tmp_path / "character.usda"))
    unbound_skel, unbound_anim = _add_unbound_skeleton(stage)
    stage.GetRootLayer().Save()
    geo_path = str(tmp_path / "character_geo.usd")

    _write_geo_layer(stage, geo_path)

    geo_stage = Usd.Stage.Open(geo_path)
    assert not geo_stage.GetPrimAtPath(unbound_skel.GetPath()).IsValid()
    assert not geo_stage.GetPrimAtPath(unbound_anim.GetPath()).IsValid()


def test_split_character_usd_unbound_skeleton_excluded_from_all_outputs(tmp_path):
    path = str(tmp_path / "character.usda")
    stage = _build_character_stage(path)
    unbound_skel, unbound_anim = _add_unbound_skeleton(stage)
    stage.GetRootLayer().Save()

    geo_path, skel_path, anim_path = split_character_usd(path)

    for output_path in (geo_path, skel_path, anim_path):
        output_stage = Usd.Stage.Open(output_path)
        assert not output_stage.GetPrimAtPath(unbound_skel.GetPath()).IsValid()
        assert not output_stage.GetPrimAtPath(unbound_anim.GetPath()).IsValid()


def test_write_skel_layer_content_visible_via_default_traverse(tmp_path):
    """A prior bug authored the Skeleton's ancestor chain with `over` specs,
    which USD's IsDefined() treats as invisible to Usd.Stage.Traverse()'s
    default predicate even though direct GetPrimAtPath() access still
    resolved values -- meaning skel.usd would appear empty in usdview or any
    other tool that walks the stage instead of hardcoding paths.
    """
    stage = _build_character_stage(str(tmp_path / "character.usda"))
    bindings = _discover_bindings(stage)
    geo_path = str(tmp_path / "character_geo.usd")
    skel_path = str(tmp_path / "character_skel.usd")
    _write_geo_layer(stage, geo_path)

    _write_skel_layer(stage, bindings, geo_path, skel_path)

    skel_stage = Usd.Stage.Open(skel_path)
    traversed = {str(p.GetPath()) for p in skel_stage.Traverse()}
    assert "/Character/Skel" in traversed
    assert "/Character/Geom/box" in traversed
    assert "/Character/Geom/box/blink" in traversed


def test_write_anim_layer_content_visible_via_default_traverse(tmp_path):
    """Same class of bug as test_write_skel_layer_content_visible_via_default_traverse,
    but more severe for anim.usd: it has no defaultPrim and references
    nothing, so an all-`over` ancestor chain leaves no defining opinion
    anywhere in the file at all -- the Animation prim would be invisible to
    Traverse() even though GetPrimAtPath() still resolves its attributes.
    """
    stage = _build_character_stage(str(tmp_path / "character.usda"))
    bindings = _discover_bindings(stage)
    anim_path = str(tmp_path / "character_anim.usd")

    _write_anim_layer(stage, bindings, anim_path)

    anim_stage = Usd.Stage.Open(anim_path)
    traversed = {str(p.GetPath()) for p in anim_stage.Traverse()}
    assert "/Character/Skel/Anim" in traversed
