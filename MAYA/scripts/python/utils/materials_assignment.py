from maya import cmds
from pxr import Usd, UsdGeom, UsdShade
import maya.api.OpenMaya as om


DEFAULT_SCOPE_NAME = "Looks"


def build_materials_assignment_stage(
    dag_object,
    scope_name=DEFAULT_SCOPE_NAME,
    purpose="",
    asset_version=None,
    asset_name=None,
):
    """
    依據指定 DAG 物件下的所有 shape 節點，建構材質指派的 in-memory USD Stage。

    Args:
        dag_object: Maya 中 DAG 物件名稱
        scope_name: USD 中放置材質的 Scope 名稱
        purpose: UsdShade 材質繫結用途，預設 "" 代表 allPurpose
        asset_version: 寫入 root prim 的 assetInfo:version
        asset_name: 寫入 root prim 的 assetInfo:name

    Returns:
        建構完成的 Usd.Stage；若沒有 shape 子節點或無法建立根 prim 則回傳 None。
    """
    shape_children = cmds.listRelatives(dag_object, ad=True, f=True, typ="mesh")
    if not shape_children:
        return None

    om_list = om.MSelectionList()
    for shape in shape_children:
        om_list.add(shape)

    stage = Usd.Stage.CreateInMemory()
    mesh_list = [om.MFnMesh(om_list.getDagPath(i)) for i in range(om_list.length())]

    for i, mesh in enumerate(mesh_list):
        path = om_list.getDagPath(i).fullPathName()
        shaders, indices = mesh.getConnectedShaders(0)
        prim = stage.OverridePrim(path.replace("|", "/"))
        root_children = stage.GetPrimAtPath("/").GetAllChildren()
        if not root_children:
            continue
        root = root_children[0]
        scope = stage.OverridePrim(root.GetPath().AppendChild(scope_name))

        if len(shaders) == 1:
            shading_group_name = om.MFnDependencyNode(shaders[0]).name()
            material_conns = cmds.listConnections(
                shading_group_name + ".surfaceShader"
            )
            if not material_conns:
                continue
            material_name = material_conns[0].replace(":", "_")
            usd_material = UsdShade.Material.Define(
                stage, scope.GetPath().AppendChild(material_name)
            )
            UsdShade.MaterialBindingAPI(prim).Bind(usd_material, materialPurpose=purpose)
        elif len(shaders) > 1:
            shading_group_names = [om.MFnDependencyNode(x).name() for x in shaders]
            for shader_index, shading_group_name in enumerate(shading_group_names):
                material_conns = cmds.listConnections(
                    shading_group_name + ".surfaceShader"
                )
                if not material_conns:
                    continue
                material_name = material_conns[0].replace(":", "_")
                geom_subset = UsdGeom.Subset.Define(
                    stage, prim.GetPath().AppendChild(material_name)
                )
                geom_subset.CreateElementTypeAttr("face")
                geom_subset.CreateIndicesAttr(
                    [
                        face_idx
                        for face_idx, sg_idx in enumerate(indices)
                        if sg_idx == shader_index
                    ]
                )
                usd_material = UsdShade.Material.Define(
                    stage, scope.GetPath().AppendChild(material_name)
                )
                UsdShade.MaterialBindingAPI(geom_subset).Bind(
                    usd_material, materialPurpose=purpose
                )

    root_children = stage.GetPrimAtPath("/").GetAllChildren()
    if not root_children:
        return None
    root_prim = root_children[0]
    if asset_version:
        root_prim.SetAssetInfoByKey("version", asset_version)
    if asset_name:
        root_prim.SetAssetInfoByKey("name", asset_name)
    stage.SetDefaultPrim(root_prim)

    return stage
