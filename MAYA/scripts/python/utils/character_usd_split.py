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


def _define_ancestor_chain(layer: Sdf.Layer, path: Sdf.Path) -> None:
    """Ensure every ancestor of ``path`` (down to but not including the
    absolute root) has a ``def`` (not ``over``) prim spec in ``layer``.

    ``Sdf.CopySpec`` requires the destination's ancestor path to already
    exist as a spec, and ``Sdf.CreatePrimInLayer`` creates missing ancestors
    as ``over`` by default. But USD's ``UsdPrim.IsDefined()`` walks the full
    ancestor chain: a single ``over`` anywhere in it makes every descendant
    invisible to ``Usd.Stage.Traverse()``'s default predicate, even one that
    would otherwise resolve to ``def`` through a reference (confirmed
    empirically -- a local ``over`` opinion suppresses a weaker referenced
    ``def`` for the same prim). Every ancestor must be forced to ``def``
    (typeless is fine) explicitly, not just the immediate parent.
    """
    for ancestor in path.GetParentPath().GetPrefixes():
        ancestor_spec = Sdf.CreatePrimInLayer(layer, ancestor)
        ancestor_spec.specifier = Sdf.SpecifierDef


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


def _write_geo_layer(stage: Usd.Stage, geo_path: str) -> None:
    """Write a geometry-only copy of ``stage`` with all skeleton content removed.

    Copies the full input layer, then removes every Skeleton prim, every
    Animation prim, and every BlendShape prim -- found by type, not by the
    discovered bindings list, since real mayaUSDExport output can contain
    Skeleton/Animation prims that are never bound to any mesh (e.g. Maya
    FK/IK control-rig joints exported as their own Skeleton+Animation pair).
    Unbound skeleton content has no skinning role, so it belongs in neither
    skel.usd nor anim.usd; geo.usd is the only place it would otherwise
    survive, and it must not. Also strips the applied SkelBindingAPI schema
    plus all ``skel:``-namespaced properties from every prim on the copied
    stage that carries them (not just the skinned meshes -- the schema can
    be applied on a SkelRoot or other ancestor too).
    """
    geo_layer = Sdf.Layer.CreateNew(geo_path)
    Sdf.CopySpec(stage.GetRootLayer(), Sdf.Path("/"), geo_layer, Sdf.Path("/"))
    geo_stage = Usd.Stage.Open(geo_layer)

    skel_content_paths = [
        prim.GetPath()
        for prim in geo_stage.TraverseAll()
        if prim.IsA(UsdSkel.Skeleton) or prim.IsA(UsdSkel.Animation) or prim.IsA(UsdSkel.BlendShape)
    ]
    for prim_path in skel_content_paths:
        if geo_stage.GetPrimAtPath(prim_path).IsValid():
            geo_stage.RemovePrim(prim_path)

    # SkelBindingAPI can be applied on any prim -- the SkelRoot or another
    # ancestor, not only the skinned mesh -- since UsdSkel bindings are
    # namespace-inherited. Strip the schema and skel:-namespaced properties
    # wherever it's actually applied so geo.usd never carries a dangling
    # skel:skeleton/skel:animationSource pointing at content removed above.
    for prim in geo_stage.Traverse():
        if "SkelBindingAPI" not in prim.GetAppliedSchemas():
            continue
        prim.RemoveAPI(UsdSkel.BindingAPI)
        for prop_name in list(prim.GetPropertyNames()):
            if prop_name.startswith("primvars:skel:") or prop_name.startswith("skel:"):
                prim.RemoveProperty(prop_name)

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
    skel_path: str,
) -> None:
    """Write a standalone stage carrying the skeleton and skinning overlay.

    References nothing — geo.usd, skel.usd, and anim.usd are three
    independent files; composing them (reference, payload, or sublayer) is
    left entirely to whoever consumes the split. For each skinned mesh, this
    writes a typeless ``def`` prim (not ``over``: with no reference bringing
    in geo.usd's ``def Mesh``, an ``over`` mesh -- or an ``over`` anywhere in
    its ancestor chain -- would be invisible to Usd.Stage.Traverse()'s
    default predicate, along with everything nested under it, e.g. a
    BlendShape). Leaving typeName unauthored means composing this mesh path
    with geo.usd's later still resolves to the real Mesh type; only the
    skinning data (SkelBindingAPI, joint indices/weights, geomBindTransform,
    skeleton/blendshape relationships, all copied verbatim from ``stage``)
    is actually new content here. The actual Skeleton and BlendShape prims
    are ``def``-ed directly. The Animation prim is deliberately excluded (it
    belongs only in anim.usd), and any ``skel:animationSource`` on the
    copied Skeleton is cleared.
    """
    skel_stage = Usd.Stage.CreateNew(skel_path)

    # Up-axis/units aren't inherited by a standalone CreateNew() stage, so
    # copy them explicitly -- otherwise skel.usd opened on its own reports
    # USD's defaults, which may not match the source stage's.
    if stage.HasAuthoredMetadata("upAxis"):
        UsdGeom.SetStageUpAxis(skel_stage, UsdGeom.GetStageUpAxis(stage))
    if stage.HasAuthoredMetadata("metersPerUnit"):
        UsdGeom.SetStageMetersPerUnit(skel_stage, UsdGeom.GetStageMetersPerUnit(stage))

    src_default_prim = stage.GetDefaultPrim()
    root_prim = skel_stage.DefinePrim(src_default_prim.GetPath())
    skel_stage.SetDefaultPrim(root_prim)

    for binding in bindings:
        _define_ancestor_chain(skel_stage.GetRootLayer(), binding.skeleton_path)
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
            _define_ancestor_chain(skel_stage.GetRootLayer(), mesh_path)
            mesh_spec = Sdf.CreatePrimInLayer(skel_stage.GetRootLayer(), mesh_path)
            mesh_spec.specifier = Sdf.SpecifierDef
            over_binding = UsdSkel.BindingAPI.Apply(skel_stage.GetPrimAtPath(mesh_path))

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
    _logger.info("Wrote skeleton+binding USD: %s (standalone, references nothing)", skel_path)


def _write_anim_layer(stage: Usd.Stage, bindings: List[_SkelBinding], anim_path: str) -> None:
    """Write a standalone copy of every Animation prim found by discovery.

    References nothing: the output is meant to be swappable per-shot
    against whatever skel.usd it's eventually paired with downstream.
    """
    anim_stage = Usd.Stage.CreateNew(anim_path)

    # Time-sample playback metadata isn't inherited by a standalone
    # CreateNew() stage, so copy it explicitly. Guarded by HasAuthoredMetadata
    # so a source stage that never set these doesn't get misleading defaults
    # (e.g. framesPerSecond, which always reports a value even when unauthored).
    if stage.HasAuthoredMetadata("startTimeCode"):
        anim_stage.SetStartTimeCode(stage.GetStartTimeCode())
    if stage.HasAuthoredMetadata("endTimeCode"):
        anim_stage.SetEndTimeCode(stage.GetEndTimeCode())
    if stage.HasAuthoredMetadata("framesPerSecond"):
        anim_stage.SetFramesPerSecond(stage.GetFramesPerSecond())
    if stage.HasAuthoredMetadata("timeCodesPerSecond"):
        anim_stage.SetTimeCodesPerSecond(stage.GetTimeCodesPerSecond())

    for binding in bindings:
        if binding.anim_path is None:
            continue
        _define_ancestor_chain(anim_stage.GetRootLayer(), binding.anim_path)
        Sdf.CopySpec(
            stage.GetRootLayer(), binding.anim_path,
            anim_stage.GetRootLayer(), binding.anim_path,
        )

    anim_stage.GetRootLayer().Save()
    _logger.info("Wrote standalone animation USD: %s", anim_path)


def split_character_usd(
    character_usd_path: str,
    output_dir: Optional[str] = None,
) -> Tuple[str, str, str]:
    """Split a combined character USD (geo + skeleton + animation) into
    three independent files: <name>_geo.usd, <name>_skel.usd, <name>_anim.usd.

    All three files are standalone and reference nothing — composing them
    (reference, payload, or sublayer) is left entirely to whoever consumes
    the split. Neither ``_skel.usd`` nor ``_anim.usd`` authors
    ``skel:animationSource`` — wiring a specific anim clip to the rig is a
    downstream pipeline decision.

    Args:
        character_usd_path: Path to the combined character USD, as written
            by e.g. ``cmds.mayaUSDExport(...)``. Must exist on disk.
        output_dir: Directory for the three outputs. ``None`` (default)
            writes them next to ``character_usd_path``.

    Returns:
        ``(geo_path, skel_path, anim_path)``.

    Raises:
        FileNotFoundError: If ``character_usd_path`` does not exist.
        ValueError: If the stage has no resolvable UsdSkel binding at all
            (nothing to split — this function is for rigged characters), or
            if the stage has no defaultPrim authored.
    """
    if not os.path.isfile(character_usd_path):
        raise FileNotFoundError(f"USD file not found: {character_usd_path}")

    stage = Usd.Stage.Open(character_usd_path)
    bindings = _discover_bindings(stage)
    if not bindings:
        raise ValueError(f"No UsdSkel bindings found in: {character_usd_path}")
    if not stage.GetDefaultPrim().IsValid():
        raise ValueError(f"Stage has no defaultPrim: {character_usd_path}")

    out_dir = output_dir or os.path.dirname(os.path.abspath(character_usd_path))
    base = os.path.splitext(os.path.basename(character_usd_path))[0]
    geo_path = os.path.join(out_dir, f"{base}_geo.usd")
    skel_path = os.path.join(out_dir, f"{base}_skel.usd")
    anim_path = os.path.join(out_dir, f"{base}_anim.usd")

    try:
        _write_geo_layer(stage, geo_path)
        _write_skel_layer(stage, bindings, skel_path)
        _write_anim_layer(stage, bindings, anim_path)
    except Exception:
        # Don't leave a partial split on disk -- downstream tooling globbing
        # for *_geo.usd etc. can't distinguish a completed split from a failed one.
        for output_path in (geo_path, skel_path, anim_path):
            if os.path.exists(output_path):
                os.remove(output_path)
        raise

    _logger.info(
        "Split %s -> geo=%s skel=%s anim=%s",
        character_usd_path, geo_path, skel_path, anim_path,
    )
    return geo_path, skel_path, anim_path
