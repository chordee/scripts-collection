# Derived from Houdini 22.0.429's husdplugins/houdiniprocedurals/invokegraph.py.
#
# Adds an opt-in per-input `--skin` flag: an entry in args['inputs'] written as
# 'skinprims:input_1 --skin' imports that input with UsdSkel skinning and
# blendshapes evaluated at the render frame, instead of the bind pose the stock
# procedural reads, and drops every prim under it that has no skeleton binding.
# Entries without the flag behave exactly as in the stock procedural.

import hou
import husd

from pxr import Gf, Sdf, Usd, UsdGeom, UsdRender, UsdSkel

SKIN_FLAG = '--skin'

# SkelAnimation attributes that drive skinning and blendshapes.
SKEL_ANIM_ATTRS = ('translations', 'rotations', 'scales', 'blendShapeWeights')

def __getRenderInfo(stage, args, tc):
    cam_path = None
    resolution = None

    try:
        render_settings_dict = args['__husk_settings']['RenderSettings']
        cam_path = render_settings_dict.get('renderCameraPath')
        resolution = render_settings_dict.get('resolution')
    except KeyError:
        pass
    if cam_path is None or resolution is None:
        render_settings = UsdRender.Settings.GetStageRenderSettings(stage)
        if not render_settings:
            # Try to find *any* RenderSettings prim
            for prim in iter(Usd.PrimRange(stage.GetPrimAtPath('/Render'))):
                render_settings = UsdRender.Settings(prim)
                if render_settings:
                    break
        # TODO - even in the absence of a RenderSettings should we still
        #        search for a camera?
        if not render_settings:
            return {}
        if cam_path is None:
            targets = render_settings.GetCameraRel().GetTargets()
            if targets:
                cam_path = targets[0]
        if resolution is None:
            resolution = render_settings.GetResolutionAttr().Get(tc)
            resolution = husd.typeutils.convertFromGf(resolution)

    if cam_path is None or resolution is None:
        return {}

    camprim = stage.GetPrimAtPath(cam_path)
    if not camprim:
        return {}
    cam = UsdGeom.Camera(camprim)
    haper = cam.GetHorizontalApertureAttr().Get(tc)
    vaper = cam.GetVerticalApertureAttr().Get(tc)
    focal = cam.GetFocalLengthAttr().Get(tc)
    clip = cam.GetClippingRangeAttr().Get(tc)
    clip = husd.typeutils.convertFromGf(clip)
    xform = cam.ComputeLocalToWorldTransform(tc)
    xform = hou.Matrix4(husd.typeutils.convertFromGf(xform))
    shutter_open = cam.GetShutterOpenAttr().Get(tc)
    shutter_close = cam.GetShutterCloseAttr().Get(tc)

    return {
        'camera': {
            'path': str(cam_path),
            'horizontalAperture': haper,
            'verticalAperture': vaper,
            'focalLength': focal,
            'clippingRange': clip,
            'localToWorldTransform': xform,
            'shutterOpen': shutter_open,
            'shutterClose': shutter_close
        },
        'resolution': resolution
    }

def __parseInput(entry):
    name, *flags = entry.split()
    unknown = [flag for flag in flags if flag != SKIN_FLAG]
    if unknown:
        raise ValueError(
            'Unknown flag(s) {} on input {!r}'.format(' '.join(unknown), entry))
    return name, SKIN_FLAG in flags

def __findSkelRoots(stage, paths):
    roots = []
    for path in paths:
        prim = stage.GetPrimAtPath(path)
        if not prim:
            continue
        root = UsdSkel.Root.Find(prim)
        if root:
            roots.append(root)
            continue
        it = iter(Usd.PrimRange(prim))
        for descendant in it:
            if descendant.IsA(UsdSkel.Root):
                roots.append(UsdSkel.Root(descendant))
                it.PruneChildren()
    unique = {root.GetPath(): root for root in roots}
    return list(unique.values())

def __skinnedStage(stage, paths, frame):
    """Bake skinning for the SkelRoots under `paths` at `frame`.

    The bake goes into a masked copy of the stage whose own session layer
    sublayers the original's, so the render stage is never modified.
    Returns the copy and the paths of the prims that carry a skeleton binding.
    """
    roots = __findSkelRoots(stage, paths)
    if not roots:
        return None, set()

    cache = UsdSkel.Cache()
    bound = set()
    mask_paths = set()
    anim_paths = set()
    for root in roots:
        mask_paths.add(root.GetPath())
        cache.Populate(root, Usd.PrimDefaultPredicate)
        for binding in cache.ComputeSkelBindings(root, Usd.PrimDefaultPredicate):
            skel = binding.GetSkeleton()
            mask_paths.add(skel.GetPath())
            anim_query = cache.GetSkelQuery(skel).GetAnimQuery()
            if anim_query:
                anim_paths.add(anim_query.GetPrim().GetPath())
            for target in binding.GetSkinningTargets():
                bound.add(target.GetPrim().GetPath().pathString)
    mask_paths |= anim_paths

    session = Sdf.Layer.CreateAnonymous('skinned-session')
    session.subLayerPaths.append(stage.GetSessionLayer().identifier)
    skin_stage = Usd.Stage.OpenMasked(
        stage.GetRootLayer(), session, stage.GetPathResolverContext(),
        Usd.StagePopulationMask(sorted(mask_paths)), Usd.Stage.LoadNone)
    skin_stage.SetLoadRules(stage.GetLoadRules())
    skin_stage.MuteAndUnmuteLayers(stage.GetMutedLayers(), [])
    skin_stage.SetEditTarget(session)

    # BakeSkinning only bakes at the time samples that fall inside its
    # interval, so a frame between two animation samples (a motion blur
    # subframe, or animation keyed on twos) would bake the rest pose.
    # Pinning the interpolated animation at `frame` guarantees a sample there.
    tc = Usd.TimeCode(frame)
    for anim_path in anim_paths:
        anim_prim = skin_stage.GetPrimAtPath(anim_path)
        for name in SKEL_ANIM_ATTRS:
            attr = anim_prim.GetAttribute(name)
            if attr and attr.ValueMightBeTimeVarying():
                attr.Set(attr.Get(tc), tc)

    for root in roots:
        UsdSkel.BakeSkinning(UsdSkel.Root(skin_stage.GetPrimAtPath(root.GetPath())),
                             Gf.Interval(frame, frame))
    return skin_stage, bound

def __keepPrims(geo, keep_paths):
    # `path` comes from unpackusd, whose std:boundables traversal stops at the
    # first boundable. A SkelRoot is boundable, so for an input at or above a
    # SkelRoot this only resolves to the individual skinned prims because
    # BakeSkinning rewrites SkelRoots to Xforms.
    path_attrib = geo.findPrimAttrib('path')
    if path_attrib is None:
        return
    geo.deletePrims([geoprim for geoprim in geo.prims()
                     if geoprim.attribValue(path_attrib) not in keep_paths])

def __proceduralAtFrame(prim, args, frame):

    tc = Usd.TimeCode(frame)

    pv_api = UsdGeom.PrimvarsAPI(prim)

    verbs = hou.sopNodeTypeCategory().nodeVerbs()

    graph = hou.Geometry()
    graph_path = hou.text.expandString(args['graph'])
    graph.loadFromFile(graph_path)
    sesi_signed = hou.lop._isProceduralSigned(graph_path)

    geos = [graph,]

    if 'inputs' in args:
        rule = hou.LopSelectionRule()
        stage = prim.GetStage()
        unpack = verbs['unpackusd::2.0']
        unpack.setParms({
            'output': 1
        })
        for input in args['inputs']:
            input, skin = __parseInput(input)
            rel = prim.GetRelationship(input)
            paths = [s.pathString for s in rel.GetForwardedTargets()]
            geo = hou.Geometry()
            rule.setPathPattern(' '.join(paths))
            if skin:
                skin_stage, bound = __skinnedStage(stage, paths, frame)
                if skin_stage:
                    geo.importUsdStage(skin_stage, rule, purpose='guide default render', frame=frame)
                    unpack.execute(geo, [geo])
                    __keepPrims(geo, bound)
            else:
                geo.importUsdStage(stage, rule, purpose='guide default render', frame=frame)
                unpack.execute(geo, [geo])
            geos.append(geo)

    overrides = hou.Geometry()
    overrides.addAttrib(hou.attribType.Global, '__preview', False)
    if '__preview' in args:
        overrides.setGlobalAttribValue('__preview', args['__preview'])
    overrides.addAttrib(hou.attribType.Global, 'parms', {})
    overrides.addAttrib(hou.attribType.Global, '__settings', {})
    overrides.setGlobalAttribValue('__settings', __getRenderInfo(prim.GetStage(), args, tc))
    if 'overrides' in args:
        attr = {}
        for override in args['overrides']:
            pv_val = pv_api.GetPrimvar(args['overrides'][override]).Get(hou.frame())
            if isinstance(pv_val, Sdf.AssetPath):
                pv_val = pv_val.resolvedPath if pv_val.resolvedPath else pv_val.path
            elif isinstance(pv_val, Sdf.AssetPathArray):
                pv_val = [v.resolvedPath if v.resolvedPath else v.path for v in pv_val]
            elif husd.typeutils.isGfType(pv_val):
                pv_val = husd.typeutils.convertFromGf(pv_val)
            attr[override] = pv_val
        overrides.setGlobalAttribValue('parms', attr)
    geos.append(overrides)

    result = hou.Geometry()

    invoke = verbs['invokegraph']
    invoke.setParms({
        'method': 1,
        'inputgroup': 'inputs'
    })
    invoke.executeAtTime(result, geos, hou.frameToTime(frame), False)

    if not sesi_signed and '__validateGeo' in args and args['__validateGeo']:
        for geoprim in result.prims():
            if not isinstance(geoprim, hou.Face) or geoprim.isClosed():
                raise RuntimeError('Procedural generated geometry other than points and curves')

    non_primvar_attrs = ''
    if 'non_primvar_attrs' in args:
        non_primvar_attrs = args['non_primvar_attrs']

    attrib = verbs['attribcreate::2.0']
    attrs = [
        {
            'name#': 'usdconfigcustomattribs',
            'class#': 0,
            'type#': 3,
            'string#': non_primvar_attrs
        },
        {
            'name#': 'usdconfigdefineonlyleafprims',
            'class#': 0,
            'type#': 3,
            'string#': "1"
        }
    ]

    # Geometry generated from the graph is placed into the stage based on the
    # following rules for the primpath (i.e., the first matching rule wins):
    # 1 - Use the procedural args' `output` value
    # 2 - Use the `path` attribute (per-prim or per-point) from the SOP geo
    # 3 - Use the path the procedural API schema was applied to
    if 'output' in args:
        anchor_primpath = prim.GetPath()
        relpath = Sdf.Path(pv_api.GetPrimvar(args['output']).Get())
        abspath = relpath.MakeAbsolutePath(anchor_primpath)
        output_primpath = abspath.pathString
    elif not result.findPrimAttrib('path') and not result.findPointAttrib('path'):
        output_primpath = prim.GetPath().pathString
    else:
        output_primpath = None
    if output_primpath:
        attrs += [
            {
                'name#': 'path',
                'class#': 1,  # per-primitive, for meshes/curves
                'type#': 3,
                'string#': output_primpath
            },
            {
                'name#': 'path',
                'class#': 2,  # per-point, for points
                'type#': 3,
                'string#': output_primpath
            }
        ]

    attrib.setParms({'numattr': attrs})
    attrib.execute(result, [result])

    return result

def procedural(prim, args):
    result = []
    frame = hou.frame()
    if prim.HasAPI('MotionAPI'):
        tc = Usd.TimeCode(frame)
        info = __getRenderInfo(prim.GetStage(), args, tc)
        cam_info = info.get('camera', {})
        shutter_open = cam_info.get('shutterOpen')
        shutter_close = cam_info.get('shutterClose')
        motion_api = UsdGeom.MotionAPI(prim)
        samples = motion_api.GetNonlinearSampleCountAttr().Get(tc) or 1
        if shutter_open is not None and shutter_close is not None and samples > 1:
            segments = samples - 1
            dt = (shutter_close - shutter_open) / segments
            for i in range(samples):
                t = frame + shutter_open + i * dt
                result.append((t, __proceduralAtFrame(prim, args, t)))
        else:
            result.append((frame, __proceduralAtFrame(prim, args, frame)))
    else:
        result.append((frame, __proceduralAtFrame(prim, args, frame)))
    return result