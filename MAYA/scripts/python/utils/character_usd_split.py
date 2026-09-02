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
