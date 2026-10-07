"""Tests for husdplugins/houdiniprocedurals/invokegraph_skinned.py.

The procedural lives outside chd_toolkits, so it is loaded straight from its
file. Expected skinned positions are computed independently with
UsdSkel.SkinningQuery / BlendShapeQuery rather than BakeSkinning, which is
what the procedural itself uses.
"""

import importlib.util
from pathlib import Path

import pytest

pytest.importorskip("hou")
pytest.importorskip("pxr")

import hou
from pxr import Gf, Usd, UsdGeom, UsdSkel, Vt

PROCEDURAL_FILE = (
    Path(__file__).resolve().parents[3]
    / "husdplugins" / "houdiniprocedurals" / "invokegraph_skinned.py"
)


def _load_procedural():
    spec = importlib.util.spec_from_file_location("invokegraph_skinned", PROCEDURAL_FILE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


igs = _load_procedural()
parse_input = getattr(igs, "__parseInput")
skinned_stage = getattr(igs, "__skinnedStage")
keep_prims = getattr(igs, "__keepPrims")


def _quad(offset):
    return [Gf.Vec3f(offset, 1, 0), Gf.Vec3f(offset + 1, 1, 0),
            Gf.Vec3f(offset + 1, 2, 0), Gf.Vec3f(offset, 2, 0)]


def _build_stage():
    """SkelRoot /World/Char whose arm joint turns 0 -> 90 degrees over frames 1-10.

    Under /World/Char/Geo: a skinned mesh with vertex normals, a skinned mesh
    with faceVarying normals and a blendshape (one level deeper), a rigidly
    bound mesh, and an explicitly unbound mesh. /World/Static sits outside the
    SkelRoot, and the animation source lives outside it at /Anims/Wave.
    """
    stage = Usd.Stage.CreateInMemory()
    UsdGeom.Xform.Define(stage, "/World")
    root = UsdSkel.Root.Define(stage, "/World/Char")
    UsdGeom.Xformable(root).AddTranslateOp().Set(Gf.Vec3d(5, 0, 0))

    skel = UsdSkel.Skeleton.Define(stage, "/World/Char/Skel")
    joints = ["root", "root/arm"]
    skel.CreateJointsAttr(joints)
    bind = [Gf.Matrix4d(1), Gf.Matrix4d(1).SetTranslate(Gf.Vec3d(0, 1, 0))]
    skel.CreateBindTransformsAttr(bind)
    skel.CreateRestTransformsAttr(bind)

    anim = UsdSkel.Animation.Define(stage, "/Anims/Wave")
    anim.CreateJointsAttr(joints)
    anim.CreateTranslationsAttr([Gf.Vec3f(0), Gf.Vec3f(0, 1, 0)])
    anim.CreateScalesAttr([Gf.Vec3h(1), Gf.Vec3h(1)])
    rotations = anim.CreateRotationsAttr()
    for frame, degrees in ((1, 0), (10, 90)):
        quat = Gf.Quatf(Gf.Rotation(Gf.Vec3d(0, 0, 1), degrees).GetQuat())
        rotations.Set([Gf.Quatf(1), quat], frame)
    anim.CreateBlendShapesAttr(["smile"])
    weights = anim.CreateBlendShapeWeightsAttr()
    weights.Set([0.0], 1)
    weights.Set([1.0], 10)
    UsdSkel.BindingAPI.Apply(skel.GetPrim()).CreateAnimationSourceRel().SetTargets(
        [anim.GetPath()])

    geo = UsdGeom.Xform.Define(stage, "/World/Char/Geo")
    UsdSkel.BindingAPI.Apply(geo.GetPrim()).CreateSkeletonRel().SetTargets([skel.GetPath()])
    UsdGeom.Xform.Define(stage, "/World/Char/Geo/sub")

    def mesh(path, offset, rigid=False, skinned=True):
        m = UsdGeom.Mesh.Define(stage, path)
        m.CreatePointsAttr(_quad(offset))
        m.CreateFaceVertexCountsAttr([4])
        m.CreateFaceVertexIndicesAttr([0, 1, 2, 3])
        if skinned:
            binding = UsdSkel.BindingAPI.Apply(m.GetPrim())
            if rigid:
                binding.CreateJointIndicesPrimvar(True, 1).Set([1])
                binding.CreateJointWeightsPrimvar(True, 1).Set([1.0])
            else:
                binding.CreateJointIndicesPrimvar(False, 1).Set([1, 1, 1, 1])
                binding.CreateJointWeightsPrimvar(False, 1).Set([1, 1, 1, 1])
        return m

    body = mesh("/World/Char/Geo/body", 0)
    body.CreateNormalsAttr([Gf.Vec3f(1, 0, 0)] * 4)
    body.SetNormalsInterpolation("vertex")

    face = mesh("/World/Char/Geo/sub/face", 2)
    face.CreateNormalsAttr([Gf.Vec3f(1, 0, 0)] * 4)
    face.SetNormalsInterpolation("faceVarying")
    smile = UsdSkel.BlendShape.Define(stage, "/World/Char/Geo/sub/face/smile")
    smile.CreateOffsetsAttr([Gf.Vec3f(0, 0, 1)])
    smile.CreatePointIndicesAttr([0])
    face_binding = UsdSkel.BindingAPI(face.GetPrim())
    face_binding.CreateBlendShapesAttr(["smile"])
    face_binding.CreateBlendShapeTargetsRel().SetTargets([smile.GetPath()])

    mesh("/World/Char/Geo/helmet", 4, rigid=True)
    prop = mesh("/World/Char/Geo/prop", 6, skinned=False)
    UsdSkel.BindingAPI.Apply(prop.GetPrim()).CreateSkeletonRel().SetTargets([])
    mesh("/World/Static", 8, skinned=False)
    return stage


def _round(vec):
    return tuple(round(c, 4) for c in vec)


def _expected_world_points(stage, frame):
    tc = Usd.TimeCode(frame)
    root = UsdSkel.Root(stage.GetPrimAtPath("/World/Char"))
    cache = UsdSkel.Cache()
    cache.Populate(root, Usd.PrimDefaultPredicate)
    expected = {}
    for binding in cache.ComputeSkelBindings(root, Usd.PrimDefaultPredicate):
        skel_query = cache.GetSkelQuery(binding.GetSkeleton())
        xforms = skel_query.ComputeSkinningTransforms(tc)
        skel_to_world = UsdGeom.Xformable(
            binding.GetSkeleton().GetPrim()).ComputeLocalToWorldTransform(tc)
        for skinning in binding.GetSkinningTargets():
            prim = skinning.GetPrim()
            points = Vt.Vec3fArray(UsdGeom.PointBased(prim).GetPointsAttr().Get(tc))
            if skinning.HasBlendShapes():
                blend = UsdSkel.BlendShapeQuery(UsdSkel.BindingAPI(prim))
                weights = skel_query.GetAnimQuery().ComputeBlendShapeWeights(tc)
                sub_weights, blend_indices, sub_indices = blend.ComputeSubShapeWeights(weights)
                blend.ComputeDeformedPoints(
                    sub_weights, blend_indices, sub_indices,
                    blend.ComputeBlendShapePointIndices(),
                    blend.ComputeSubShapePointOffsets(), points)
            if skinning.IsRigidlyDeformed():
                rigid = skinning.ComputeSkinnedTransform(xforms, tc)
                world = [skel_to_world.Transform(rigid.Transform(Gf.Vec3d(p))) for p in points]
            else:
                skinning.ComputeSkinnedPoints(xforms, points, tc)
                world = [skel_to_world.Transform(Gf.Vec3d(p)) for p in points]
            expected[prim.GetPath().pathString] = sorted(_round(p) for p in world)
    return expected


def _import_skinned(stage, paths, frame):
    skin_stage, bound = skinned_stage(stage, paths, frame)
    rule = hou.LopSelectionRule()
    rule.setPathPattern(" ".join(paths))
    geo = hou.Geometry()
    geo.importUsdStage(skin_stage, rule, purpose="guide default render", frame=frame)
    unpack = hou.sopNodeTypeCategory().nodeVerbs()["unpackusd::2.0"]
    unpack.setParms({"output": 1})
    unpack.execute(geo, [geo])
    keep_prims(geo, bound)
    return geo


def _points_by_path(geo):
    return {
        geoprim.attribValue("path"):
            sorted(_round(v.point().position()) for v in geoprim.vertices())
        for geoprim in geo.prims()
    }


SKINNED_PRIMS = {
    "/World/Char/Geo/body", "/World/Char/Geo/sub/face", "/World/Char/Geo/helmet",
}


def test_parse_input_without_flag():
    assert parse_input("skinprims:input_1") == ("skinprims:input_1", False)


def test_parse_input_with_skin_flag():
    assert parse_input("skinprims:input_1 --skin") == ("skinprims:input_1", True)


def test_parse_input_rejects_unknown_flag():
    with pytest.raises(ValueError, match="--skins"):
        parse_input("skinprims:input_1 --skins")


@pytest.mark.parametrize("paths", [
    ["/World/Char/Geo"],
    ["/World/Char"],
    ["/World"],
    ["/World/Char/Geo/sub/face", "/World/Char/Geo/body"],
])
@pytest.mark.parametrize("frame", [1, 10, 5.5, 7.25])
def test_skinned_points_match_usdskel(paths, frame):
    stage = _build_stage()
    got = _points_by_path(_import_skinned(stage, paths, frame))
    expected = _expected_world_points(stage, frame)
    assert got
    for path, points in got.items():
        assert points == expected[path], path


def test_unbound_prims_are_dropped():
    got = _points_by_path(_import_skinned(_build_stage(), ["/World"], 10))
    assert set(got) == SKINNED_PRIMS


def test_frame_10_is_not_bind_pose():
    stage = _build_stage()
    got = _points_by_path(_import_skinned(stage, ["/World/Char/Geo/body"], 10))
    assert got["/World/Char/Geo/body"] == sorted(
        [(5.0, 1.0, 0.0), (5.0, 2.0, 0.0), (4.0, 2.0, 0.0), (4.0, 1.0, 0.0)])


def test_normals_follow_the_skinning():
    geo = _import_skinned(_build_stage(), ["/World/Char/Geo/sub/face"], 10)
    normals = {_round(v.attribValue("N")) for v in geo.prims()[0].vertices()}
    assert normals == {(0.0, 1.0, 0.0)}


def test_input_without_skel_root_yields_no_stage():
    skin_stage, bound = skinned_stage(_build_stage(), ["/World/Static"], 10)
    assert skin_stage is None
    assert bound == set()


def test_render_stage_is_left_untouched():
    stage = _build_stage()
    before = stage.GetSessionLayer().ExportToString()
    _import_skinned(stage, ["/World/Char"], 5.5)
    assert stage.GetSessionLayer().ExportToString() == before
