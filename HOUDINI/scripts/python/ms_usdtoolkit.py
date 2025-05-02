from pxr import Usd, UsdGeom, Sdf, UsdShade
import hou
from typing import Optional, Iterable, Union

def computePrimScale(prim: Usd.Prim, frame: int) -> Optional[Iterable[float]]:
    """
    computePrimScale Compute world space scale of primitive

    Args:
        prim (Usd.Prim): USD primtive
        frame (int): frame

    Returns:
        Optional[Iterable[float]]: vector of scale
    """

    xform = UsdGeom.Xformable(prim)
    if not xform:
        return None
    mat = xform.ComputeLocalToWorldTransform(frame)
    scale = [v.GetLength() for v in mat.ExtractRotationMatrix()]
    return scale


def primtiveXform(prim: Usd.Prim, frame: int) -> Optional[hou.Matrix4]:
    """
    primtiveXform fetch primitive world space matrix

    Args:
        prim (Usd.Prim): USD primtive
        frame (int): frame

    Returns:
        Optional[hou.Matrix4]: Houdini Matrix
    """
    
    xform = UsdGeom.Xformable(prim)
    if not xform:
        return None
    usd_xform = xform.ComputeLocalToWorldTransform(frame)
    h_xform = hou.Matrix4(usd_xform)
    return h_xform

def get_material_from_prim(prim: Usd.Prim) -> Optional[UsdShade.Material]:
    """
    get_material_from_prim Returns the directly bound UsdShade.Material for a given USD primitive, if any.

    Args:
        prim (Usd.Prim): The USD primitive to query.

    Returns:
        Optional[UsdShade.Material]: The directly bound material, or None if not found.
    """
    materialBinding_api = UsdShade.MaterialBindingAPI(prim)
    direct_binding = materialBinding_api.GetDirectBinding()
    material = direct_binding.GetMaterial()
    if material.GetPrim().IsValid():
        return material
    return None
    

def get_all_asset_paths_from_prim(prim: Usd.Prim) -> Iterable[str]:
    """
    get_all_asset_paths_from_prim All asset paths in Primitive

    Args:
        prim (Usd.Prim): USD primtive

    Returns:
        Iterable[str]: List of file path strings
    """
    asset_paths = []
    for attr in prim.GetAttributes():
        if attr.GetTypeName() == Sdf.ValueTypeNames.Asset:
            timesamples = attr.GetTimeSamples()
            if len(timesamples) > 0:
                asset_paths.extend([attr.Get(t).resolvedPath for t in timesamples])
            else:
                val = attr.Get()
                if val:
                    asset_paths.append(attr.Get().resolvedPath)
    return list(set(asset_paths))

def get_clip_names(prim: Usd.Prim) -> Optional[Iterable[str]]:
    """
    get_clip_names _summary_

    Args:
        prim (Usd.Prim): USD primitive

    Returns:
        Optional[Iterable[str]]: list of clip names
    """
    if not prim.HasMetadata('clips'):
        return None
    clips = prim.GetMetadata('clips').keys()
    return clips

def get_clip_sequences_from_prim(prim: Usd.Prim, clip: str = 'default') -> Optional[Iterable[str]]:
    """
    get_clip_sequences_from_prim _summary_

    Args:
        prim (Usd.Prim): USD primitive
        clip (str, optional): Clip name. Defaults to 'default'.

    Returns:
        Optional[Iterable[str]]: list of asset paths
    """
    if not prim.HasMetadata('clips'):
        return None
    metadata = prim.GetMetadata('clips')
    if not clip in metadata.keys():
        return None
    sequences = [x.resolvedPath for x in metadata[clip]['assetPaths']]
    return list(set(sequences))

def get_all_clip_sequenes_from_prim(prim: Usd.Prim) -> Optional[Iterable[str]]:
    """
    get_all_clip_sequenes_from_prim All sequence asset paths in value clip primitive.

    Args:
        prim (Usd.Prim): USD primitive

    Returns:
        Optional[Iterable[str]]: list of all asset paths
    """
    if not prim.HasMetadata('clips'):
        return None
    clips = get_clip_names(prim)
    if not clips:
        return None
    sequences = []
    for clip in clips:
        clip_sequences = get_clip_sequences_from_prim(prim, clip)
        if clip_sequences:
            sequences.extend(clip_sequences)
    return list(set(sequences))
    
    
def get_all_asset_paths_from_stage(stage: Usd.Stage, prim_path: Union[str, Sdf.Path] = '/') -> Iterable[str]:
    """
    get_all_asset_paths_from_stage All asset paths in USD stage

    Args:
        stage (Usd.Stage): USD stage
        prim_path (Union[str, Sdf.Path], optional): Search root primitive. Defaults to '/'.

    Returns:
        Iterable[str]: list of all asset paths
    """
    asset_paths = []
    start_prim = stage.GetPrimAtPath(prim_path)
    iterator = iter(Usd.PrimRange(start_prim))
    for prim in iterator:
        asset_paths.extend(get_all_asset_paths_from_prim(prim))
    return list(set(asset_paths))

def get_all_clip_sequenes_from_stage(stage: Usd.Stage, prim_path: Union[str, Sdf.Path] = '/') -> Iterable[str]:
    """
    get_all_clip_sequenes_from_stage All sequence asset paths in USD stage

    Args:
        stage (Usd.Stage): Usd stage
        prim_path (Union[str, Sdf.Path], optional): Search root primitive. Defaults to '/'.

    Returns:
        Iterable[str]: list of all asset paths
    """
    sequences = []
    start_prim = stage.GetPrimAtPath(prim_path)
    iterator = iter(Usd.PrimRange(start_prim))
    for prim in iterator:
        if prim.HasMetadata('clips'):
            sequences.extend(get_all_clip_sequenes_from_prim(prim))
    return list(set(sequences))

def get_all_layers_in_layer(usd_layer: Union[str, Sdf.Layer]) -> Iterable[str]:
    """
    get_all_layers_in_layer Get all layer file in some usd file

    Args:
        usd_layer (Union[str, Sdf.Layer]): USD file path or Sdf.Layer

    Returns:
        Iterable[str]: a list of all usd layer files
    """
    all_layers = []
    if isinstance(usd_layer, Sdf.Layer):
        main_layer = usd_layer
    else:
        main_layer = Sdf.Layer.FindOrOpen(usd_layer)
    if not main_layer:
        return None
    def list_layers(layer, level = 1) -> None:
        nonlocal all_layers
        refs = layer.GetExternalReferences()
        if len(refs) > 0:
            for extref in refs:
                abs_path = layer.ComputeAbsolutePath(extref)
                all_layers.append(abs_path)
                list_layers(Sdf.Layer.FindOrOpen(abs_path), level + 1)

    list_layers(main_layer)
    return all_layers

