# -*- coding: utf-8 -*-
"""USD utilities for Maya: stage creation, sublayer / reference helpers."""

import logging
import os
from typing import Optional, Union

import maya.cmds as cmds
import mayaUsd.ufe
import mayaUsd_createStageWithNewLayer
from pxr import Sdf, Usd


_logger = logging.getLogger(__name__)


def _normalize_layer_path(path: str) -> str:
    """Normalize a sublayer path for dedup comparisons (forward slashes, no redundant separators)."""
    return os.path.normpath(path).replace("\\", "/")


def ensure_usd_plugin() -> None:
    """Load ``mayaUsdPlugin`` if it has not been loaded yet."""
    if not cmds.pluginInfo("mayaUsdPlugin", query=True, loaded=True):
        cmds.loadPlugin("mayaUsdPlugin")


def create_empty_stage(name: Optional[str] = None) -> Usd.Stage:
    """Create a new empty USD stage backed by a fresh anonymous root layer.

    Args:
        name: Optional name for the created transform node. If ``None``, the
            Maya default name is kept.

    Returns:
        The newly created ``Usd.Stage``.

    Raises:
        RuntimeError: If the proxy shape could not be created, the rename
            could not locate its parent / shape, or ``mayaUsd.ufe.getStage``
            failed to return a stage.
    """
    ensure_usd_plugin()

    proxy_shape_path = mayaUsd_createStageWithNewLayer.createStageWithNewLayer()

    if name:
        parents = cmds.listRelatives(proxy_shape_path, parent=True, fullPath=True) or []
        if not parents:
            raise RuntimeError(
                f"Could not find parent transform of {proxy_shape_path}"
            )
        transform_node = parents[0]
        new_transform = cmds.rename(transform_node, name)
        shapes = cmds.listRelatives(new_transform, shapes=True, fullPath=True) or []
        if not shapes:
            raise RuntimeError(
                f"Renamed transform {new_transform} has no shape node"
            )
        proxy_shape_path = shapes[0]

    stage = mayaUsd.ufe.getStage(proxy_shape_path)
    if stage is None:
        raise RuntimeError(
            f"Failed to acquire Usd.Stage from {proxy_shape_path}"
        )
    return stage


def create_stage_from_file(file_path: str, name: Optional[str] = None) -> Usd.Stage:
    """Create a proxy shape and load the given USD file into it.

    Args:
        file_path: Absolute or relative path to a USD file. Must exist on disk.
        name: Optional transform node name. If ``None``, the file basename
            (with non-alphanumeric characters replaced by ``_``) is used.

    Returns:
        The loaded ``Usd.Stage``.

    Raises:
        FileNotFoundError: If ``file_path`` does not exist.
        RuntimeError: If ``mayaUsd.ufe.getStage`` fails to return a stage.
    """
    ensure_usd_plugin()

    if not os.path.isfile(file_path):
        raise FileNotFoundError(f"USD file not found: {file_path}")

    if not name:
        base_name = os.path.splitext(os.path.basename(file_path))[0]
        name = "".join(c if c.isalnum() or c == "_" else "_" for c in base_name)

    transform_node = cmds.createNode("transform", name=name)
    transform_full = cmds.ls(transform_node, long=True)[0]
    proxy_shape = cmds.createNode(
        "mayaUsdProxyShape",
        name=f"{transform_node}Shape",
        parent=transform_full,
    )
    proxy_shape_full = cmds.ls(proxy_shape, long=True)[0]

    cmds.setAttr(f"{proxy_shape_full}.filePath", file_path, type="string")

    stage = mayaUsd.ufe.getStage(proxy_shape_full)
    if stage is None:
        raise RuntimeError(
            f"Failed to acquire Usd.Stage from {proxy_shape_full}"
        )
    return stage


def add_sublayer(
    stage: Usd.Stage,
    sublayer_path: Union[str, Sdf.Path],
    index: int = 0,
) -> str:
    """Add a sublayer to the stage's root layer.

    Comparison against existing sublayers is done on a normalized path
    (forward slashes, collapsed dots), so paths that only differ in
    separator style or redundant ``./`` segments are treated as duplicates.

    Args:
        stage: Target stage. ``None`` raises ``ValueError``.
        sublayer_path: Path to the USD file to add as a sublayer.
        index: Insertion position. ``0`` is the strongest layer. If
            ``index`` is >= the current sublayer count the path is appended.

    Returns:
        The path that was added (or already present), as a string.

    Raises:
        ValueError: If ``stage`` is falsy.
    """
    if not stage:
        raise ValueError("Provided stage is None or invalid.")

    root_layer = stage.GetRootLayer()
    sublayer_path_str = str(sublayer_path)
    normalized = _normalize_layer_path(sublayer_path_str)

    existing_normalized = {_normalize_layer_path(p) for p in root_layer.subLayerPaths}
    if normalized in existing_normalized:
        _logger.info("Sublayer '%s' already exists in stage.", sublayer_path_str)
        return sublayer_path_str

    if index >= len(root_layer.subLayerPaths):
        root_layer.subLayerPaths.append(sublayer_path_str)
    else:
        root_layer.subLayerPaths.insert(index, sublayer_path_str)

    _logger.info("Added sublayer '%s' at index %d.", sublayer_path_str, index)
    return sublayer_path_str


def add_reference(
    stage: Usd.Stage,
    prim_path: Union[str, Sdf.Path],
    ref_file_path: str,
    ref_prim_path: Optional[Union[str, Sdf.Path]] = None,
    on_root_layer: bool = True,
) -> Usd.Prim:
    """Add a reference to a prim, creating an ``Xform`` if the prim does not exist.

    Args:
        stage: Target stage. ``None`` raises ``ValueError``.
        prim_path: Path of the prim to apply the reference on.
        ref_file_path: USD file path used as the reference asset.
        ref_prim_path: Optional prim path inside the referenced file. ``None``
            (the default) means use the referenced file's defaultPrim.
        on_root_layer: When ``True`` (default) the reference is authored on
            the stage's root layer via ``Usd.EditContext``; when ``False``
            the current edit target is used.

    Returns:
        The prim that received the reference.

    Raises:
        ValueError: If ``stage`` is falsy.
        RuntimeError: If ``UsdReferences.AddReference`` returns ``False``.
    """
    if not stage:
        raise ValueError("Provided stage is None or invalid.")

    prim_path_str = str(prim_path)
    sdf_ref_prim_path = Sdf.Path(str(ref_prim_path)) if ref_prim_path else Sdf.Path()

    def _author() -> Usd.Prim:
        prim = stage.GetPrimAtPath(prim_path_str)
        if not prim.IsValid():
            prim = stage.DefinePrim(prim_path_str, "Xform")
        added = prim.GetReferences().AddReference(
            assetPath=str(ref_file_path),
            primPath=sdf_ref_prim_path,
        )
        if not added:
            raise RuntimeError(
                f"AddReference failed for prim '{prim_path_str}' -> "
                f"'{ref_file_path}' (primPath={sdf_ref_prim_path!r})"
            )
        return prim

    if on_root_layer:
        with Usd.EditContext(stage, stage.GetRootLayer()):
            prim = _author()
    else:
        prim = _author()

    target_repr = str(ref_prim_path) if ref_prim_path else "defaultPrim"
    _logger.info(
        "Added reference to '%s' -> '%s' (target prim: %s).",
        prim_path_str,
        ref_file_path,
        target_repr,
    )
    return prim
