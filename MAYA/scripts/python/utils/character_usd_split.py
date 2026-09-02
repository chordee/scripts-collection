# -*- coding: utf-8 -*-
"""Split a combined Maya-USD character export into geo / skel / anim USD files.

Meant to be called manually right after ``cmds.mayaUSDExport(...)`` — this
is a plain function, not a registered Maya-USD Export Chaser plugin.
"""

import logging
import os
from typing import List, Optional, Tuple

from pxr import Sdf, Usd, UsdGeom, UsdSkel


_logger = logging.getLogger(__name__)


class _SkelBinding:
    """One SkelRoot's resolved skeleton/animation/mesh/blendshape graph."""

    def __init__(
        self,
        skeleton_path: Sdf.Path,
        anim_path: Optional[Sdf.Path],
        skinned_mesh_paths: List[Sdf.Path],
        blend_shape_paths: List[Sdf.Path],
    ) -> None:
        self.skeleton_path = skeleton_path
        self.anim_path = anim_path
        self.skinned_mesh_paths = skinned_mesh_paths
        self.blend_shape_paths = blend_shape_paths


def _discover_bindings(stage: Usd.Stage) -> List[_SkelBinding]:
    """Resolve every skinning binding on the stage via UsdSkel.Cache.

    Schema-based discovery, not path-guessing: works regardless of how deep
    or where mayaUSDExport happens to place the Skeleton / Animation /
    BlendShape prims, as long as every ancestor prim between a SkelRoot and
    its skinned meshes is explicitly typed (UsdSkel.Cache silently skips
    skinning targets under an untyped ancestor prim).
    """
    cache = UsdSkel.Cache()
    result: List[_SkelBinding] = []

    for prim in stage.Traverse():
        if not prim.IsA(UsdSkel.Root):
            continue
        skel_root = UsdSkel.Root(prim)
        cache.Populate(skel_root, Usd.PrimDefaultPredicate)

        for binding in cache.ComputeSkelBindings(skel_root, Usd.PrimDefaultPredicate):
            skeleton_prim = binding.GetSkeleton().GetPrim()
            skel_query = cache.GetSkelQuery(binding.GetSkeleton())
            anim_query = skel_query.GetAnimQuery()
            anim_path = anim_query.GetPrim().GetPath() if anim_query else None

            skinned_mesh_paths = [
                sq.GetPrim().GetPath() for sq in binding.GetSkinningTargets()
            ]

            blend_shape_paths: List[Sdf.Path] = []
            for mesh_path in skinned_mesh_paths:
                mesh_binding = UsdSkel.BindingAPI(stage.GetPrimAtPath(mesh_path))
                for bs_path in mesh_binding.GetBlendShapeTargetsRel().GetTargets():
                    if bs_path not in blend_shape_paths:
                        blend_shape_paths.append(bs_path)

            result.append(
                _SkelBinding(
                    skeleton_path=skeleton_prim.GetPath(),
                    anim_path=anim_path,
                    skinned_mesh_paths=skinned_mesh_paths,
                    blend_shape_paths=blend_shape_paths,
                )
            )

    return result


def _write_geo_layer(stage: Usd.Stage, bindings: List[_SkelBinding], geo_path: str) -> None:
    """Write a geometry-only copy of ``stage`` with all skeleton content removed.

    Copies the full input layer, then removes every Skeleton prim (which
    also removes any Animation prim nested under it), every BlendShape
    prim, and — on every skinned mesh — the applied SkelBindingAPI schema
    plus all ``skel:``-namespaced properties.
    """
    geo_layer = Sdf.Layer.CreateNew(geo_path)
    Sdf.CopySpec(stage.GetRootLayer(), Sdf.Path("/"), geo_layer, Sdf.Path("/"))
    geo_stage = Usd.Stage.Open(geo_layer)

    for binding in bindings:
        if geo_stage.GetPrimAtPath(binding.skeleton_path).IsValid():
            geo_stage.RemovePrim(binding.skeleton_path)

        for bs_path in binding.blend_shape_paths:
            if geo_stage.GetPrimAtPath(bs_path).IsValid():
                geo_stage.RemovePrim(bs_path)

        for mesh_path in binding.skinned_mesh_paths:
            mesh_prim = geo_stage.GetPrimAtPath(mesh_path)
            mesh_prim.RemoveAPI(UsdSkel.BindingAPI)
            for prop_name in list(mesh_prim.GetPropertyNames()):
                if prop_name.startswith("primvars:skel:") or prop_name.startswith("skel:"):
                    mesh_prim.RemoveProperty(prop_name)

    geo_stage.GetRootLayer().Save()
    _logger.info("Wrote geo-only USD: %s", geo_path)


def _copy_primvar(src_binding, dst_binding, get_src_pv, create_dst_pv) -> None:
    """Copy one UsdGeom.Primvar (interpolation, elementSize, value) across bindings.

    ``get_src_pv``/``create_dst_pv`` are the matching getter/creator pair,
    e.g. ``lambda b: b.GetJointIndicesPrimvar()`` and
    ``lambda b, constant, element_size: b.CreateJointIndicesPrimvar(constant, element_size)``.
    No-ops if the source primvar was never authored.
    """
    src_pv = get_src_pv(src_binding)
    if not src_pv.IsDefined():
        return
    is_constant = src_pv.GetInterpolation() == UsdGeom.Tokens.constant
    dst_pv = create_dst_pv(dst_binding, is_constant, src_pv.GetElementSize())
    dst_pv.Set(src_pv.Get())


def _write_skel_layer(
    stage: Usd.Stage,
    bindings: List[_SkelBinding],
    geo_path: str,
    skel_path: str,
) -> None:
    """Write a stage that references ``geo_path`` and overlays skinning data.

    For each skinned mesh, adds an ``over`` re-authoring SkelBindingAPI,
    joint indices/weights, geomBindTransform, and the skeleton/blendshape
    relationships (copied verbatim from ``stage``) onto the mesh referenced
    in from ``geo_path`` — no mesh geometry is duplicated. The actual
    Skeleton and BlendShape prims are ``def``-ed directly (they're new
    content, not overrides of anything in geo.usd). The Animation prim is
    deliberately excluded (it belongs only in anim.usd), and any
    ``skel:animationSource`` on the copied Skeleton is cleared.
    """
    skel_stage = Usd.Stage.CreateNew(skel_path)
    geo_relpath = os.path.relpath(geo_path, os.path.dirname(skel_path)).replace("\\", "/")

    src_default_prim = stage.GetDefaultPrim()
    root_prim = skel_stage.DefinePrim(src_default_prim.GetPath())
    root_prim.GetReferences().AddReference(geo_relpath)
    skel_stage.SetDefaultPrim(root_prim)

    for binding in bindings:
        Sdf.CopySpec(
            stage.GetRootLayer(), binding.skeleton_path,
            skel_stage.GetRootLayer(), binding.skeleton_path,
        )
        if binding.anim_path is not None and skel_stage.GetPrimAtPath(binding.anim_path).IsValid():
            skel_stage.RemovePrim(binding.anim_path)
        copied_skel_prim = skel_stage.GetPrimAtPath(binding.skeleton_path)
        UsdSkel.BindingAPI(copied_skel_prim).GetAnimationSourceRel().ClearTargets(True)

        for mesh_path in binding.skinned_mesh_paths:
            src_mesh_binding = UsdSkel.BindingAPI(stage.GetPrimAtPath(mesh_path))
            over_mesh = skel_stage.OverridePrim(mesh_path)
            over_binding = UsdSkel.BindingAPI.Apply(over_mesh)

            _copy_primvar(
                src_mesh_binding, over_binding,
                lambda b: b.GetJointIndicesPrimvar(),
                lambda b, c, e: b.CreateJointIndicesPrimvar(c, e),
            )
            _copy_primvar(
                src_mesh_binding, over_binding,
                lambda b: b.GetJointWeightsPrimvar(),
                lambda b, c, e: b.CreateJointWeightsPrimvar(c, e),
            )

            geom_bind_attr = src_mesh_binding.GetGeomBindTransformAttr()
            if geom_bind_attr.HasAuthoredValue():
                over_binding.CreateGeomBindTransformAttr().Set(geom_bind_attr.Get())

            over_binding.CreateSkeletonRel().SetTargets([binding.skeleton_path])

            bs_names = src_mesh_binding.GetBlendShapesAttr().Get()
            if bs_names:
                over_binding.CreateBlendShapesAttr(bs_names)
                over_binding.CreateBlendShapeTargetsRel().SetTargets(
                    src_mesh_binding.GetBlendShapeTargetsRel().GetTargets()
                )

        # BlendShape prims nest under the mesh path, so copy them only after
        # the `over` specs above have established that path in this layer.
        for bs_path in binding.blend_shape_paths:
            Sdf.CopySpec(stage.GetRootLayer(), bs_path, skel_stage.GetRootLayer(), bs_path)

    skel_stage.GetRootLayer().Save()
    _logger.info("Wrote skeleton+binding USD: %s (references %s)", skel_path, geo_relpath)
