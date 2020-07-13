import maya.cmds as cmds
import maya.api.OpenMaya as om
from pxr import Usd, UsdGeom, UsdShade
# import numpy as np 

def export(dagObject, merge = False, scopeName = 'Looks', purpose = 'all', assetVersion = None, assetName = None):
    merge = False
    """
    In current, Merge Transform and Shape nodes UNSUPPORT!!
    Because pxrUsdExport doesn't really merge them when Shape Object parent another Shape object directly in Maya Outliner.
    """
    if not dagObject:
        return

    shapeChildren = cmds.listRelatives(dagObject, ad = True, f = True, typ = 'shape')
    
    omList = om.MSelectionList()
    for shape in shapeChildren:
        omList.add(shape)
    
    stage = Usd.Stage.CreateInMemory()

    meshLsit = [om.MFnMesh(omList.getDagPath(i)) for i in range(omList.length())]

    for i, mesh in zip(range(omList.length()), meshLsit):
        path = omList.getDagPath(i).fullPathName()
        shaders, indices = mesh.getConnectedShaders(0)
        prim = stage.OverridePrim(path.replace('|', '/'))
        root = stage.GetPrimAtPath('/').GetAllChildren()[0]
        scope = stage.OverridePrim(root.GetPath().AppendChild(scopeName))
        if len(shaders) == 1:
            shadingGroup_name = om.MFnDependencyNode(shaders[0]).name()
            usdMaterial = UsdShade.Material.Define(stage, scope.GetPrim().GetPath().AppendChild(shadingGroup_name))
            UsdShade.MaterialBindingAPI(prim).Bind(usdMaterial)
        elif len(shaders) > 1:
            shadingGroup_names = [om.MFnDependencyNode(x).name() for x in shaders]
            shader_index = 0
            for shadingGroup_name in shadingGroup_names:
                geomSubset = UsdGeom.Subset.Define(stage, prim.GetPrim().GetPath().AppendChild(shadingGroup_name))
                geomSubset.CreateElementTypeAttr('face')
                geomSubset.CreateIndicesAttr([i for i, x in enumerate(indices) if x == shader_index])
                usdMaterial = UsdShade.Material.Define(stage, scope.GetPrim().GetPath().AppendChild(shadingGroup_name))
                UsdShade.MaterialBindingAPI(geomSubset).Bind(usdMaterial, materialPurpose = purpose)
                shader_index += 1
    
    rootPrim = stage.GetPrimAtPath('/').GetAllChildren()[0]
    if assetVersion:
        rootPrim.SetAssetInfoByKey('version', assetVersion)
    if assetName:
        rootPrim.SetAssetInfoByKey('name', assetName)
    stage.SetDefaultPrim(rootPrim)
    return stage


if __name__ == '__main__':
    sel = cmds.ls(sl = True)[0]

    filenames = cmds.fileDialog2(fm = 0, startingDirectory = 'C:/', fileFilter = "USD (*.usd *.usda)")
    if filenames:
        filename = filenames[0]
        stage = export(sel)
        stage.Export(filename)