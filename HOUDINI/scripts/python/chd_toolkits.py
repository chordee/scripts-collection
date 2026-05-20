"""Houdini Python toolkit: geometry/numpy bridge, USD prim queries, and layer traversal helpers."""

import importlib.util
from typing import List, Optional, Union

import numpy as np

import hou
from pxr import Gf, Sdf, Usd, UsdGeom, UsdShade


# ---------------------------------------------------------------------------
# Houdini geometry / numpy bridge
# ---------------------------------------------------------------------------

def matrix_manipulate(
    matrix: Union[hou.Matrix3, hou.Matrix4],
    data: np.ndarray,
) -> Optional[np.ndarray]:
    """Apply a Houdini matrix to an Nx3 numpy vector array (row vectors)."""
    if data.ndim != 2 or data.shape[1] != 3:
        return None
    if isinstance(matrix, hou.Matrix3):
        matrix = hou.Matrix4(matrix)
    mat = np.array(matrix.asTupleOfTuples(), dtype=np.float32)
    ext = np.ones((data.shape[0], 1), dtype=np.float32)
    homog = np.concatenate((data, ext), axis=1)
    return (homog @ mat)[:, :3]


def point_attrib_to_numpy(geo: hou.Geometry, attr: str = "P") -> Optional[np.ndarray]:
    """Read a numeric point attribute into a numpy array shaped (npoints, size)."""
    point_attr = geo.findPointAttrib(attr)
    if point_attr is None:
        return None

    dtype_enum = point_attr.dataType()
    size = point_attr.size()

    if dtype_enum == hou.attribData.Int:
        raw = geo.pointIntAttribValuesAsString(attr, int_type=hou.numericData.Int32)
        return np.frombuffer(raw, dtype=np.int32).reshape(-1, size)
    if dtype_enum == hou.attribData.Float:
        raw = geo.pointFloatAttribValuesAsString(attr, float_type=hou.numericData.Float32)
        return np.frombuffer(raw, dtype=np.float32).reshape(-1, size)
    return None


# ---------------------------------------------------------------------------
# 2D convolution
# ---------------------------------------------------------------------------

def convolve2d(
    image: np.ndarray,
    kernel: np.ndarray,
    padding: int = 0,
    strides: int = 1,
    pad_mode: Optional[str] = None,
) -> np.ndarray:
    """Naive 2D convolution. For production use prefer ``scipy_convolve2d`` below."""
    if not isinstance(strides, int) or strides < 1:
        raise ValueError(f"strides must be an integer >= 1, got {strides!r}")
    if not isinstance(padding, int) or padding < 0:
        raise ValueError(f"padding must be a non-negative integer, got {padding!r}")

    if padding > 0:
        mode = "constant" if pad_mode is None else pad_mode
        image_padded = np.pad(image, padding, mode=mode)
    else:
        image_padded = image

    x_kern, y_kern = kernel.shape
    x_img, y_img = image_padded.shape
    if x_kern > x_img or y_kern > y_img:
        raise ValueError(
            f"kernel shape {kernel.shape} larger than padded image shape "
            f"{image_padded.shape}"
        )

    x_out = (x_img - x_kern) // strides + 1
    y_out = (y_img - y_kern) // strides + 1
    out_dtype = np.result_type(image.dtype, kernel.dtype, np.float64)
    output = np.zeros((x_out, y_out), dtype=out_dtype)

    for y in range(0, y_img - y_kern + 1, strides):
        for x in range(0, x_img - x_kern + 1, strides):
            output[x // strides, y // strides] = (
                kernel * image_padded[x : x + x_kern, y : y + y_kern]
            ).sum()
    return output


if importlib.util.find_spec("scipy") is not None:
    from scipy import signal as _scipy_signal

    def scipy_convolve2d(
        image: np.ndarray,
        kernel: np.ndarray,
        mode: str = "same",
        boundary: str = "symm",
    ) -> np.ndarray:
        """Thin wrapper over scipy.signal.convolve2d."""
        return _scipy_signal.convolve2d(image, kernel, mode=mode, boundary=boundary)


# ---------------------------------------------------------------------------
# USD prim transforms
# ---------------------------------------------------------------------------

def compute_prim_scale(
    prim: Usd.Prim,
    time: Union[int, float, Usd.TimeCode] = Usd.TimeCode.Default(),
) -> Optional[List[float]]:
    """World-space scale vector via Gf.Matrix4d.Factor; sign flipped for mirrored xforms."""
    xform = UsdGeom.Xformable(prim)
    if not xform:
        return None
    if not isinstance(time, Usd.TimeCode):
        time = Usd.TimeCode(time)
    mat = xform.ComputeLocalToWorldTransform(time)

    factored = mat.Factor()
    if not factored[0]:
        return None
    _, rotation, scale_vec, _, _ = factored
    scale = [scale_vec[0], scale_vec[1], scale_vec[2]]
    if rotation.GetDeterminant() < 0:
        scale[0] = -scale[0]
    return scale


def primitive_xform(
    prim: Usd.Prim,
    time: Union[int, float, Usd.TimeCode] = Usd.TimeCode.Default(),
) -> Optional[hou.Matrix4]:
    """World-space transform of a prim as hou.Matrix4."""
    xform = UsdGeom.Xformable(prim)
    if not xform:
        return None
    if not isinstance(time, Usd.TimeCode):
        time = Usd.TimeCode(time)
    usd_xform = xform.ComputeLocalToWorldTransform(time)
    rows = tuple(tuple(row) for row in usd_xform)
    return hou.Matrix4(rows)


# ---------------------------------------------------------------------------
# USD material / asset / clip queries
# ---------------------------------------------------------------------------

def get_material_from_prim(prim: Usd.Prim) -> Optional[UsdShade.Material]:
    """Return the directly-bound UsdShade.Material on a prim, or None."""
    binding_api = UsdShade.MaterialBindingAPI(prim)
    direct_binding = binding_api.GetDirectBinding()
    if direct_binding.GetMaterialPath().IsEmpty():
        return None
    material = direct_binding.GetMaterial()
    if material and material.GetPrim().IsValid():
        return material
    return None


def _asset_paths_from_value(value) -> List[str]:
    if value is None:
        return []
    if isinstance(value, Sdf.AssetPath):
        return [value.resolvedPath] if value.resolvedPath else []
    # AssetArray comes back as a VtArray of Sdf.AssetPath
    out = []
    try:
        for item in value:
            if item and item.resolvedPath:
                out.append(item.resolvedPath)
    except TypeError:
        pass
    return out


def get_all_asset_paths_from_prim(prim: Usd.Prim) -> List[str]:
    """Collect resolved asset paths from all Asset/AssetArray attributes on a prim."""
    asset_paths: List[str] = []
    asset_types = {Sdf.ValueTypeNames.Asset, Sdf.ValueTypeNames.AssetArray}
    for attr in prim.GetAttributes():
        if attr.GetTypeName() not in asset_types:
            continue
        timesamples = attr.GetTimeSamples()
        if timesamples:
            for t in timesamples:
                asset_paths.extend(_asset_paths_from_value(attr.Get(t)))
        else:
            asset_paths.extend(_asset_paths_from_value(attr.Get()))
    return list(set(asset_paths))


def get_clip_names(prim: Usd.Prim) -> Optional[List[str]]:
    """Return clipSet names declared in the prim's ``clips`` metadata, or None."""
    if not prim.HasMetadata('clips'):
        return None
    return list(prim.GetMetadata('clips').keys())


def get_clip_sequences_from_prim(
    prim: Usd.Prim,
    clip: str = 'default',
) -> Optional[List[str]]:
    """Resolved asset paths from a clipSet's ``assetPaths`` entry; None if absent."""
    if not prim.HasMetadata('clips'):
        return None
    metadata = prim.GetMetadata('clips')
    clip_meta = metadata.get(clip)
    if clip_meta is None:
        return None
    asset_paths = clip_meta.get('assetPaths')
    if not asset_paths:
        return None
    return list({x.resolvedPath for x in asset_paths if x and x.resolvedPath})


def get_all_clip_sequences_from_prim(prim: Usd.Prim) -> Optional[List[str]]:
    """Union of asset paths across every clipSet on a prim."""
    clips = get_clip_names(prim)
    if not clips:
        return None
    sequences: List[str] = []
    for clip in clips:
        clip_sequences = get_clip_sequences_from_prim(prim, clip)
        if clip_sequences:
            sequences.extend(clip_sequences)
    return list(set(sequences))


def get_all_asset_paths_from_stage(
    stage: Usd.Stage,
    prim_path: Union[str, Sdf.Path] = '/',
) -> List[str]:
    """Walk the stage from prim_path and collect all asset attribute values."""
    asset_paths: List[str] = []
    start_prim = stage.GetPrimAtPath(prim_path)
    for prim in Usd.PrimRange(start_prim):
        asset_paths.extend(get_all_asset_paths_from_prim(prim))
    return list(set(asset_paths))


def get_all_clip_sequences_from_stage(
    stage: Usd.Stage,
    prim_path: Union[str, Sdf.Path] = '/',
) -> List[str]:
    """Walk the stage and union all clipSet asset paths."""
    sequences: List[str] = []
    start_prim = stage.GetPrimAtPath(prim_path)
    for prim in Usd.PrimRange(start_prim):
        if prim.HasMetadata('clips'):
            clip_sequences = get_all_clip_sequences_from_prim(prim)
            if clip_sequences:
                sequences.extend(clip_sequences)
    return list(set(sequences))


# ---------------------------------------------------------------------------
# USD layer traversal
# ---------------------------------------------------------------------------

def get_all_layers_in_layer(
    usd_layer: Union[str, Sdf.Layer],
) -> List[str]:
    """All composition asset dependencies (sublayer/reference/payload) under a layer.

    Returns absolute paths; cycles are detected to prevent infinite recursion.
    """
    if isinstance(usd_layer, Sdf.Layer):
        main_layer = usd_layer
    else:
        main_layer = Sdf.Layer.FindOrOpen(usd_layer)
    if main_layer is None:
        return []

    found: List[str] = []
    visited = {main_layer.identifier}

    def walk(layer: Sdf.Layer) -> None:
        deps = layer.GetCompositionAssetDependencies()
        for dep in deps:
            abs_path = layer.ComputeAbsolutePath(dep)
            if abs_path in visited:
                continue
            visited.add(abs_path)
            found.append(abs_path)
            sub = Sdf.Layer.FindOrOpen(abs_path)
            if sub is not None:
                walk(sub)

    walk(main_layer)
    return found
