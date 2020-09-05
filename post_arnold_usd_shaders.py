import maya.cmds as cmds
import maya.api.OpenMaya as om
from pxr import Usd, UsdShade, UsdGeom, Sdf

filename = "C:/tmp/arnold.usda"


class MtoaShadersToUSD:

    def __init__(self, filename, root):
        self.shaderMap = {}
        self.filename = filename
        self.root = root
        self.shadingGroups = getShadingGroups(root)
        self.shaderMapMaker(self.shadingGroups)

    def exportUSD(self, scope="/materials"):
        self.scope = scope
        cmds.select(self.root, r=1)
        cmds.arnoldExportAss(f=self.filename, s=1, shadowLinks=0, mask=16,
                             lightLinks=0, forceTranslateShadingEngines=1, boundingBox=1, fullPath=1)
        self.post_peocess()

    def post_peocess(self):
        stage = Usd.Stage.Open(self.filename)
        edit = Sdf.BatchNamespaceEdit()

        scope_prim = UsdGeom.Scope.Define(stage, self.scope)

        for prim in stage.Traverse():
            if prim.GetTypeName() == "Shader" and prim.GetName() in self.shaderMap.keys():
                path = prim.GetPath()
                material = UsdShade.Material.Define(
                    stage, scope_prim.GetPath().AppendPath(self.shaderMap[prim.GetName()]))
                edit.Add(path, material.GetPath().AppendPath(prim.GetName()))
                shader = UsdShade.Shader.Define(stage, prim.GetPath())
                for i in shader.GetInputs():
                    if i.HasConnectedSource() is True:
                        print(i.GetFullName())

        stage.GetRootLayer().Apply(edit)

        edit_dict = {}
        for i in edit.edits:
            edit_dict[i.currentPath] = i.newPath

        print(edit_dict)

        for prim in stage.Traverse():
            if prim.GetTypeName() == "Shader":
                shader = UsdShade.Shader.Define(stage, prim.GetPath())
                for i in shader.GetInputs():
                    attr = i.GetAttr()
                    if len(attr.GetConnections()) > 0:
                        con = attr.GetConnections()[0]
                        k = con.ReplacePrefix(
                            con.GetPrimPath(), edit_dict[con.GetPrimPath()])
                        i.ConnectToSource(k)

        print(stage.ExportToString())
        stage.Save()

    def shaderMapMaker(self, shadingGroups):
        self.shaderMap = {}
        for shadingGroup in shadingGroups:
            self.getConnectionNodes(shadingGroup, shadingGroup)
        print self.shaderMap

    def getConnectionNodes(self, node, shadingGroup):
        res = cmds.listConnections(node, d=False, c=False, p=False)
        if res:
            for shader in res:
                self.shaderMap[str(shader)] = str(shadingGroup)
                self.getConnectionNodes(shader, shadingGroup)

    def getShaderMap(self):
        return self.shaderMap


def getShadingGroups(root):
    children_meshs = cmds.listRelatives(
        root, ad=True, typ='surfaceShape', f=True)
    mesh_list = om.MSelectionList()
    for mesh in children_meshs:
        mesh_list.add(mesh)
    shadingGroup_list = []
    for i in range(mesh_list.length()):
        mesh = om.MFnMesh(mesh_list.getDagPath(i))
        shadingGroups = [om.MFnDependencyNode(
            x).name() for x in mesh.getConnectedShaders(0)[0]]
        shadingGroup_list += shadingGroups
    shadingGroup_list = list(set(shadingGroup_list))

    return shadingGroup_list


if __name__ == "__main__":
    sel = cmds.ls(sl=True)[0]

    k = MtoaShadersToUSD(filename, sel)
    k.exportUSD()
