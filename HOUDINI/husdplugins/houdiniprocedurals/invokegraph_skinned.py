import hou
import husd

from pxr import Sdf, Usd, UsdGeom, UsdRender

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
            rel = prim.GetRelationship(input)
            paths = [s.pathString for s in rel.GetForwardedTargets()]
            geo = hou.Geometry()
            rule.setPathPattern(' '.join(paths))
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