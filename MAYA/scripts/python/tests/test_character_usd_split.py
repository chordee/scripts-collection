"""Tests for utils.character_usd_split.

Pure ``pxr`` — no Maya session required. Run under hython or any Python
with ``pxr`` (``pip install usd-core``) available.
"""

import pytest

pytest.importorskip("pxr")

from pxr import Gf, Sdf, Usd, UsdGeom, UsdSkel, Vt

from utils.character_usd_split import _discover_bindings


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
