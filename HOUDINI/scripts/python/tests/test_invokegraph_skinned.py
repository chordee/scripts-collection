"""Tests for husdplugins/houdiniprocedurals/invokegraph_skinned.py.

The procedural lives outside chd_toolkits, so it is loaded straight from its
file. Expected skinned positions are computed independently with
UsdSkel.SkinningQuery / BlendShapeQuery rather than BakeSkinning, which is
what the procedural itself uses.
"""

import importlib.util
import types
from pathlib import Path

import pytest

pytest.importorskip("hou")
pytest.importorskip("pxr")

import hou
from pxr import Gf, Usd, UsdGeom, UsdRender, UsdSkel, Vt

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


def _build_stage(use_skel_root=True):
    """SkelRoot /World/Char whose arm joint turns 0 -> 90 degrees over frames 1-10.

    Under /World/Char/Geo: a skinned mesh with vertex normals, a skinned mesh
    with faceVarying normals and a blendshape (one level deeper), a rigidly
    bound mesh, and an explicitly unbound mesh. /World/Static sits outside the
    SkelRoot, and the animation source lives outside it at /Anims/Wave.
    With ``use_skel_root=False`` /World/Char is a plain Xform; every binding
    stays authored, but nothing is enclosed by a SkelRoot.
    """
    stage = Usd.Stage.CreateInMemory()
    UsdGeom.Xform.Define(stage, "/World")
    root_type = UsdSkel.Root if use_skel_root else UsdGeom.Xform
    root = root_type.Define(stage, "/World/Char")
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


def _expected_world_points(stage, frame, ordered=False):
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
            rounded = [_round(p) for p in world]
            expected[prim.GetPath().pathString] = rounded if ordered else sorted(rounded)
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
    assert parse_input("skinprims:input_1") == ("skinprims:input_1", frozenset())


def test_parse_input_with_skin_flag():
    assert parse_input("skinprims:input_1 --skin") == ("skinprims:input_1", {"--skin"})


def test_parse_input_with_skin_and_velocity_flags():
    assert parse_input("skinprims:input_1 --skin --velocity") == (
        "skinprims:input_1", {"--skin", "--velocity"})


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
    expected = {
        path: points
        for path, points in _expected_world_points(stage, frame).items()
        if any(path == p or path.startswith(p + "/") for p in paths)
    }
    assert set(got) == set(expected)
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
    skin_stage, bound = skinned_stage(
        _build_stage(use_skel_root=False), ["/World/Char/Geo/body"], 10)
    assert skin_stage is None
    assert bound == set()


def test_render_stage_is_left_untouched():
    stage = _build_stage()
    session_before = stage.GetSessionLayer().ExportToString()
    root_before = stage.GetRootLayer().ExportToString()
    _import_skinned(stage, ["/World/Char"], 5.5)
    assert stage.GetSessionLayer().ExportToString() == session_before
    assert stage.GetRootLayer().ExportToString() == root_before


class _RecordingInvoke:
    """Stands in for the invokegraph verb and keeps the geometries it receives."""

    def __init__(self):
        self.geos = None

    def setParms(self, parms):
        pass

    def executeAtTime(self, result, geos, time, add_time_dep):
        self.geos = [geo.freeze() for geo in geos]


@pytest.fixture
def stub_invoke(monkeypatch):
    invoke = _RecordingInvoke()
    verbs = dict(hou.sopNodeTypeCategory().nodeVerbs())
    verbs["invokegraph"] = invoke
    category = types.SimpleNamespace(nodeVerbs=lambda: verbs)
    monkeypatch.setattr(igs.hou, "sopNodeTypeCategory", lambda: category)
    return invoke


@pytest.fixture
def graph_file(tmp_path):
    path = tmp_path / "graph.bgeo"
    hou.Geometry().saveToFile(str(path))
    return path


def test_procedural_mixes_bind_pose_and_skinned_inputs(stub_invoke, graph_file):
    invoke = stub_invoke

    stage = _build_stage()
    proc = UsdGeom.Xform.Define(stage, "/proc").GetPrim()
    proc.CreateRelationship("bindpose:input_0").SetTargets(["/World/Char/Geo"])
    proc.CreateRelationship("skinned:input_1").SetTargets(["/World/Char/Geo"])
    args = {
        "graph": str(graph_file),
        "inputs": ["bindpose:input_0", "skinned:input_1 --skin"],
    }
    hou.setFrame(10)
    igs.procedural(proc, args)

    # geos = [graph, input_0, input_1, overrides]
    bind_pose, skinned = invoke.geos[1], invoke.geos[2]
    assert {p.attribValue("path") for p in bind_pose.prims()} == (
        SKINNED_PRIMS | {"/World/Char/Geo/prop"})
    assert set(_points_by_path(skinned)) == SKINNED_PRIMS
    assert _points_by_path(skinned) == _expected_world_points(stage, 10)
    bind_points = {_round(p.position()) for p in bind_pose.points()}
    assert (6.0, 2.0, 0.0) in bind_points          # body corner at rest
    assert (6.0, 2.0, 0.0) not in {
        point for points in _points_by_path(skinned).values() for point in points}


@pytest.mark.parametrize("version, returns_list", [
    ((21, 0, 631), False),
    ((22, 0, 429), True),
])
def test_procedural_return_type_follows_houdini_version(
        stub_invoke, graph_file, monkeypatch, version, returns_list):
    # Houdini 21's runprocedurals.py passes the return value straight to
    # hou.lop.addLockedGeometry(); Houdini 22's expects [(frame, geo), ...].
    monkeypatch.setattr(igs.hou, "applicationVersion", lambda: version)
    stage = _build_stage()
    proc = UsdGeom.Xform.Define(stage, "/proc").GetPrim()
    proc.CreateRelationship("skinned:input_0").SetTargets(["/World/Char/Geo"])
    hou.setFrame(10)

    result = igs.procedural(
        proc, {"graph": str(graph_file), "inputs": ["skinned:input_0 --skin"]})

    if returns_list:
        assert [(frame, type(geo)) for frame, geo in result] == [(10, hou.Geometry)]
    else:
        assert isinstance(result, hou.Geometry)
    assert _points_by_path(stub_invoke.geos[1]) == _expected_world_points(stage, 10)


def _add_render_camera(stage, shutter_open, shutter_close):
    camera = UsdGeom.Camera.Define(stage, "/cam")
    camera.CreateShutterOpenAttr(shutter_open)
    camera.CreateShutterCloseAttr(shutter_close)
    settings = UsdRender.Settings.Define(stage, "/Render/rs")
    settings.CreateCameraRel().SetTargets(["/cam"])
    settings.CreateResolutionAttr(Gf.Vec2i(64, 64))
    stage.SetMetadata("renderSettingsPrimPath", "/Render/rs")


def _run_procedural(stage, inputs, frame):
    """Run the procedural with every input pointing at its path; return the input geos."""
    proc = UsdGeom.Xform.Define(stage, "/proc").GetPrim()
    entries = []
    for i, (path, flags) in enumerate(inputs):
        name = "in:input_{}".format(i)
        proc.CreateRelationship(name).SetTargets([path])
        entries.append(" ".join([name] + flags))
    hou.setFrame(frame)
    return entries, proc


def _velocity_by_position(geo):
    v_attrib = geo.findPointAttrib("v")
    assert v_attrib is not None
    return {_round(p.position()): p.attribValue(v_attrib) for p in geo.points()}


def _expected_velocity_by_position(stage, frame, shutter_open, shutter_close):
    seconds = (shutter_close - shutter_open) / stage.GetTimeCodesPerSecond()
    now = _expected_world_points(stage, frame, ordered=True)
    opened = _expected_world_points(stage, frame + shutter_open, ordered=True)
    closed = _expected_world_points(stage, frame + shutter_close, ordered=True)
    return {
        p: tuple((bb - aa) / seconds for aa, bb in zip(a, b))
        for path, points in now.items()
        for p, a, b in zip(points, opened[path], closed[path])
    }


@pytest.mark.parametrize("camera_shutter", [None, (-0.5, 0.5)])
def test_velocity_on_skinned_input(stub_invoke, graph_file, camera_shutter):
    stage = _build_stage()
    if camera_shutter:
        _add_render_camera(stage, *camera_shutter)
    shutter = camera_shutter or igs.DEFAULT_SHUTTER
    entries, proc = _run_procedural(stage, [("/World/Char/Geo", ["--skin", "--velocity"])], 5.5)
    igs.procedural(proc, {"graph": str(graph_file), "inputs": entries})

    got = _velocity_by_position(stub_invoke.geos[1])
    expected = _expected_velocity_by_position(stage, 5.5, *shutter)
    assert set(got) == set(expected)
    for position, velocity in got.items():
        # float32 points over a 1/48 s shutter: allow for the amplified rounding.
        assert velocity == pytest.approx(expected[position], abs=1e-2), position
    assert any(abs(c) > 1.0 for velocity in got.values() for c in velocity)


def test_velocity_without_skin_uses_time_sampled_points(stub_invoke, graph_file):
    stage = Usd.Stage.CreateInMemory()
    stage.SetTimeCodesPerSecond(24)
    mesh = UsdGeom.Mesh.Define(stage, "/Mover")
    mesh.CreatePointsAttr(_quad(0))
    mesh.CreateFaceVertexCountsAttr([4])
    mesh.CreateFaceVertexIndicesAttr([0, 1, 2, 3])
    translate = UsdGeom.Xformable(mesh).AddTranslateOp()
    translate.Set(Gf.Vec3d(0, 0, 0), 1)
    translate.Set(Gf.Vec3d(24, 0, 0), 25)   # one unit per frame
    entries, proc = _run_procedural(stage, [("/Mover", ["--velocity"])], 10)
    igs.procedural(proc, {"graph": str(graph_file), "inputs": entries})

    for velocity in _velocity_by_position(stub_invoke.geos[1]).values():
        assert velocity == pytest.approx((24.0, 0.0, 0.0), abs=1e-3)


def test_velocity_skipped_when_topology_changes(stub_invoke, graph_file, capsys):
    stage = Usd.Stage.CreateInMemory()
    mesh = UsdGeom.Mesh.Define(stage, "/Grower")
    points, counts, indices = mesh.CreatePointsAttr(), mesh.CreateFaceVertexCountsAttr(),         mesh.CreateFaceVertexIndicesAttr()
    # Three points up to 5.6, four after: shutter open (5.25) and close (5.75)
    # see different point counts.
    points.Set(_quad(0)[:3], 5.0)
    counts.Set([3], 5.0)
    indices.Set([0, 1, 2], 5.0)
    points.Set(_quad(0), 5.6)
    counts.Set([4], 5.6)
    indices.Set([0, 1, 2, 3], 5.6)
    entries, proc = _run_procedural(stage, [("/Grower", ["--velocity"])], 5.5)
    igs.procedural(proc, {"graph": str(graph_file), "inputs": entries})

    assert stub_invoke.geos[1].findPointAttrib("v") is None
    assert "skipping --velocity" in capsys.readouterr().err
