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


def _build_character_stage(path, with_blendshape=True):
    """A SkelRoot > Xform "Geom" > Mesh "box" (skinned) + Skeleton + Animation,
    with explicitly-typed intermediate prims (untyped ancestors break
    UsdSkel.Cache discovery — see the plan's Global Constraints).
    """
    stage = Usd.Stage.CreateNew(path)
    UsdSkel.Root.Define(stage, "/Character")
    UsdGeom.Xform.Define(stage, "/Character/Geom")
    mesh = UsdGeom.Mesh.Define(stage, "/Character/Geom/box")
    mesh.CreatePointsAttr(Vt.Vec3fArray([(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)]))
    mesh.CreateFaceVertexCountsAttr(Vt.IntArray([4]))
    mesh.CreateFaceVertexIndicesAttr(Vt.IntArray([0, 1, 2, 3]))

    skel = UsdSkel.Skeleton.Define(stage, "/Character/Skel")
    skel.CreateJointsAttr(Vt.TokenArray(["root", "root/child"]))
    skel.CreateBindTransformsAttr(Vt.Matrix4dArray([Gf.Matrix4d(1), Gf.Matrix4d(1)]))
    skel.CreateRestTransformsAttr(Vt.Matrix4dArray([Gf.Matrix4d(1), Gf.Matrix4d(1)]))

    anim = UsdSkel.Animation.Define(stage, "/Character/Skel/Anim")
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
        bs = UsdSkel.BlendShape.Define(stage, "/Character/Geom/box/blink")
        bs.CreateOffsetsAttr(Vt.Vec3fArray([(0, 0, 0.1)] * 4))
        binding.CreateBlendShapesAttr(Vt.TokenArray(["blink"]))
        binding.CreateBlendShapeTargetsRel().SetTargets([bs.GetPath()])
        anim.CreateBlendShapesAttr(Vt.TokenArray(["blink"]))
        weights_attr = anim.CreateBlendShapeWeightsAttr()
        weights_attr.Set(Vt.FloatArray([0.0]), 1.0)
        weights_attr.Set(Vt.FloatArray([1.0]), 2.0)

    skel_binding = UsdSkel.BindingAPI.Apply(skel.GetPrim())
    skel_binding.CreateAnimationSourceRel().SetTargets([anim.GetPath()])

    stage.SetDefaultPrim(stage.GetPrimAtPath("/Character"))
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
    bindings = _discover_bindings(stage)
    geo_path = str(tmp_path / "character_geo.usd")

    _write_geo_layer(stage, bindings, geo_path)

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
    bindings = _discover_bindings(stage)
    geo_path = str(tmp_path / "character_geo.usd")

    _write_geo_layer(stage, bindings, geo_path)

    geo_stage = Usd.Stage.Open(geo_path)
    assert geo_stage.GetPrimAtPath("/Character/Geom/box").IsValid()


def test_write_skel_layer_references_geo_and_overlays_skinning(tmp_path):
    stage = _build_character_stage(str(tmp_path / "character.usda"))
    bindings = _discover_bindings(stage)
    geo_path = str(tmp_path / "character_geo.usd")
    skel_path = str(tmp_path / "character_skel.usd")
    _write_geo_layer(stage, bindings, geo_path)

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
    _write_geo_layer(stage, bindings, geo_path)

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
