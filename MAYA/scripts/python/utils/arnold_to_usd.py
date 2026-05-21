from maya import cmds
from pxr import Usd, UsdGeom, UsdShade, Sdf
import maya.api.OpenMaya as om


ARNOLD_EXPORT_MASK = 16  # Arnold export bitmask: shaders only
DEFAULT_SCOPE_NAME = "Looks"


class MtoaShadersToUSD:
    """
    Arnold 材質轉換與 USD 匯出工具。
    """

    def __init__(self, filename=None, root=None):
        self.shaderMap = {}
        self.filename = filename
        self.root = root

    def exportUSD(self, scope="/" + DEFAULT_SCOPE_NAME):
        """
        匯出 Arnold 材質為 USD，並進行後處理。
        """
        assert self.root is not None

        self.shadingGroups = self.getShadingGroups(self.root)
        self.scope = scope
        cmds.arnoldExportAss(
            self.root,
            f=self.filename,
            s=1,
            shadowLinks=0,
            mask=ARNOLD_EXPORT_MASK,
            lightLinks=0,
            forceTranslateShadingEngines=1,
            boundingBox=1,
            fullPath=1,
        )
        self.post_process()

    def post_process(self):
        """
        對匯出的 USD 進行命名空間與連結修正。
        """
        stage = Usd.Stage.Open(self.filename)
        edit = Sdf.BatchNamespaceEdit()

        scope_prim = UsdGeom.Scope.Define(stage, self.scope)
        shaders_scope_prim = UsdGeom.Scope.Define(stage, self.scope + "/shaders")

        for prim in stage.Traverse():
            path = prim.GetPath()
            if prim.GetTypeName() == "Shader":
                if path.pathElementCount == 1:
                    edit.Add(
                        path,
                        shaders_scope_prim.GetPath().AppendPath(
                            path.MakeRelativePath("/")
                        ),
                    )

        stage.GetRootLayer().Apply(edit)
        stage.Reload()

        for prim in stage.Traverse():
            if prim.GetTypeName() == "Shader":
                shader = UsdShade.Shader.Define(stage, prim.GetPath())
                for shader_input in shader.GetInputs():
                    attr = shader_input.GetAttr()
                    if len(attr.GetConnections()) > 0:
                        con = attr.GetConnections()[0]
                        k = con.ReplacePrefix("/", shaders_scope_prim.GetPath())
                        shader_input.ConnectToSource(k)

        for shadingGroup in self.shadingGroups:
            connection_attrs_map = {
                "surfaceShader": "surface",
                "displacementShader": "displacement",
                "volumeShader": "volume",
            }
            for connection_attr in connection_attrs_map.keys():
                maya_shader = cmds.listConnections(shadingGroup + "." + connection_attr)
                if maya_shader:
                    maya_shader = maya_shader[0]
                if maya_shader:
                    material = UsdShade.Material.Define(
                        stage, scope_prim.GetPath().AppendPath(shadingGroup)
                    )
                    shader = UsdShade.Shader.Define(
                        stage, shaders_scope_prim.GetPath().AppendPath(str(maya_shader))
                    )
                    shader.CreateOutput(
                        connection_attrs_map[connection_attr], Sdf.ValueTypeNames.Token
                    )
                    material.CreateOutput(
                        "arnold:" + connection_attrs_map[connection_attr],
                        Sdf.ValueTypeNames.Token,
                    ).ConnectToSource(shader, connection_attrs_map[connection_attr])

        stage.Save()

    def setFilename(self, filename):
        """
        設定輸出檔名。
        """
        self.filename = filename

    def getShadingGroups(self, root):
        """
        取得指定 root 下所有 shading group 名稱。
        """
        children_meshs = cmds.listRelatives(root, ad=True, typ="surfaceShape", f=True)
        if not children_meshs:
            return []
        mesh_list = om.MSelectionList()
        for mesh in children_meshs:
            mesh_list.add(mesh)
        shadingGroup_list = []
        for i in range(mesh_list.length()):
            mesh = om.MFnMesh(mesh_list.getDagPath(i))
            shader_tuple = mesh.getConnectedShaders(0)
            if not shader_tuple or not shader_tuple[0]:
                continue
            shadingGroups = [om.MFnDependencyNode(x).name() for x in shader_tuple[0]]
            shadingGroup_list += shadingGroups
        shadingGroup_list = list(set(shadingGroup_list))

        return shadingGroup_list
