from PySide2 import QtWidgets, QtCore
from maya import cmds
from pxr import Usd, UsdGeom, UsdShade, Sdf
import maya.api.OpenMaya as om


# 常數區
USD_FILE_FILTER = "USD (*.usd *.usda)"
USD_START_DIR = "C:/"
ARNOLD_EXPORT_MASK = 16
DEFAULT_SCOPE_NAME = "Looks"


class USD_Tab(QtWidgets.QWidget):
    """
    Maya USD 工具主 UI 標籤頁，提供 SkelRoot、USD Shader、材質匯出等功能。
    """

    def __init__(self, parent=None):
        super(USD_Tab, self).__init__(parent)
        self.initUI()

    def initUI(self):
        self.layout = QtWidgets.QHBoxLayout()
        self.setLayout(self.layout)
        self.buttons_layout = QtWidgets.QVBoxLayout()
        self.layout.addLayout(self.buttons_layout)

        # buttons_layout
        self.create_skelroot_btn = QtWidgets.QPushButton("Create SkelRoot Attribute")
        self.create_usd_preview_shader_btn = QtWidgets.QPushButton(
            "Build USD Preview Shader"
        )
        self.export_materials_assignment_btn = QtWidgets.QPushButton(
            "Export Materials Assignment"
        )
        self.export_arnold_materials_btn = QtWidgets.QPushButton(
            "Export Selection Arnold Materials"
        )
        self.buttons_layout.addWidget(self.create_skelroot_btn)
        self.buttons_layout.addWidget(self.create_usd_preview_shader_btn)
        self.buttons_layout.addWidget(self.export_materials_assignment_btn)
        self.buttons_layout.addWidget(self.export_arnold_materials_btn)

        self.create_skelroot_btn.clicked.connect(self.create_skelroot_action)
        self.create_usd_preview_shader_btn.clicked.connect(
            self.create_usd_preview_shader
        )
        self.export_materials_assignment_btn.clicked.connect(
            self.export_materials_assignment
        )
        self.export_arnold_materials_btn.clicked.connect(
            self.export_selection_arnold_materials
        )

        self.layout.setAlignment(QtCore.Qt.AlignTop)
        self.layout.addStretch()

    def create_skelroot_action(self):
        """
        將選取物件加上 SkelRoot 屬性。
        """
        sel = cmds.ls(sl=1, l=1)
        if not sel:
            print("Nothing be selected.")
            return
        obj = sel[0]
        cmds.addAttr(obj, ln="USD_typeName", dt="string")
        cmds.setAttr(obj + ".USD_typeName", "SkelRoot", typ="string")

    def create_usd_preview_shader(self):
        """
        彈出 USD Preview Shader 建立對話框。
        """
        dialog = Build_USD_Preview_Shader(self)
        dialog.show()

    def export_materials_assignment(
        self,
        merge=False,
        scopeName=DEFAULT_SCOPE_NAME,
        purpose="all",
        assetVersion=None,
        assetName=None,
    ):
        """
        將選取物件的材質指派資訊匯出為 USD。
        """
        sel = cmds.ls(sl=True)
        if not sel:
            print("Nothing be selected.")
            return
        dagObject = sel[0]

        shapeChildren = cmds.listRelatives(dagObject, ad=True, f=True, typ="shape")
        if not shapeChildren:
            print("No shape children found.")
            return

        omList = om.MSelectionList()
        for shape in shapeChildren:
            omList.add(shape)

        stage = Usd.Stage.CreateInMemory()

        meshList = [om.MFnMesh(omList.getDagPath(i)) for i in range(omList.length())]

        for i, mesh in zip(range(omList.length()), meshList):
            path = omList.getDagPath(i).fullPathName()
            shaders, indices = mesh.getConnectedShaders(0)
            prim = stage.OverridePrim(path.replace("|", "/"))
            root = stage.GetPrimAtPath("/").GetAllChildren()[0]
            scope = stage.OverridePrim(root.GetPath().AppendChild(scopeName))
            if len(shaders) == 1:
                shadingGroup_name = om.MFnDependencyNode(shaders[0]).name()
                material_conns = cmds.listConnections(
                    shadingGroup_name + ".surfaceShader"
                )
                if not material_conns:
                    continue
                material_name = material_conns[0]
                # change from shadingGroup name to material name
                shadingGroup_name = material_name
                usdMaterial = UsdShade.Material.Define(
                    stage, scope.GetPrim().GetPath().AppendChild(shadingGroup_name)
                )
                UsdShade.MaterialBindingAPI(prim).Bind(usdMaterial)
            elif len(shaders) > 1:
                shadingGroup_names = [om.MFnDependencyNode(x).name() for x in shaders]
                shader_index = 0
                for shadingGroup_name in shadingGroup_names:
                    material_conns = cmds.listConnections(
                        shadingGroup_name + ".surfaceShader"
                    )
                    if not material_conns:
                        continue
                    material_name = material_conns[0]
                    # change from shadingGroup name to material name
                    shadingGroup_name = material_name
                    geomSubset = UsdGeom.Subset.Define(
                        stage, prim.GetPrim().GetPath().AppendChild(shadingGroup_name)
                    )
                    geomSubset.CreateElementTypeAttr("face")
                    geomSubset.CreateIndicesAttr(
                        [i for i, x in enumerate(indices) if x == shader_index]
                    )
                    usdMaterial = UsdShade.Material.Define(
                        stage, scope.GetPrim().GetPath().AppendChild(shadingGroup_name)
                    )
                    UsdShade.MaterialBindingAPI(geomSubset).Bind(
                        usdMaterial, materialPurpose=purpose
                    )
                    shader_index += 1

        rootPrim = stage.GetPrimAtPath("/").GetAllChildren()[0]
        if assetVersion:
            rootPrim.SetAssetInfoByKey("version", assetVersion)
        if assetName:
            rootPrim.SetAssetInfoByKey("name", assetName)
        stage.SetDefaultPrim(rootPrim)

        filenames = cmds.fileDialog2(
            fm=0, startingDirectory=USD_START_DIR, fileFilter=USD_FILE_FILTER
        )
        filename = filenames[0]
        stage.Export(filename)

    def export_selection_arnold_materials(self):
        """
        將選取物件的 Arnold 材質匯出為 USD。
        """
        sel = cmds.ls(sl=True)
        if not sel:
            print("Nothing be selected.")
            return
        obj = sel[0]
        filenames = cmds.fileDialog2(fm=0, fileFilter=USD_FILE_FILTER)

        if filenames:
            filename = filenames[0]
            k = MtoaShadersToUSD(filename, obj)
            k.exportUSD()


class Build_USD_Preview_Shader(QtWidgets.QDialog):
    """
    USD Preview Shader 建立對話框。
    """

    def __init__(self, parent=None):
        super(Build_USD_Preview_Shader, self).__init__(parent)
        self.initUI()

    def initUI(self):
        self.setWindowTitle("Build USD Preview Shader")
        main_layout = QtWidgets.QVBoxLayout()
        btn_layout = QtWidgets.QHBoxLayout()
        main_layout.setSpacing(2)

        # Name horizontal layout
        name_layout = QtWidgets.QHBoxLayout()
        name_layout.addWidget(QtWidgets.QLabel("Name:"))
        self.shader_name_lineedit = QtWidgets.QLineEdit()
        name_layout.addWidget(self.shader_name_lineedit)
        main_layout.addLayout(name_layout)

        # Textures layout
        textures_list = [
            "diffuse",
            "emissive",
            "occlusion",
            "opacity",
            "ior",
            "metallic",
            "roughness",
            "specular",
            "normal",
            "displacement",
        ]

        self.texture_layouts = dict()
        for n in textures_list:
            self.texture_layouts[n] = Texture_Layout(n)
            main_layout.addLayout(self.texture_layouts[n])

        # Buttons Layout
        self.create_btn = QtWidgets.QPushButton("Create")
        self.cancel_btn = QtWidgets.QPushButton("Cancel")
        btn_layout.addWidget(self.create_btn)
        btn_layout.addWidget(self.cancel_btn)
        main_layout.addLayout(btn_layout)
        main_layout.setAlignment(QtCore.Qt.AlignTop)
        self.setLayout(main_layout)

        self.create_btn.clicked.connect(self.create_shader)
        self.cancel_btn.clicked.connect(self.close_widget)

    def close_widget(self):
        self.close()

    def create_shader(self):
        """
        建立 USD Preview Shader 節點與貼圖連結。
        """
        shader_name = None
        if self.shader_name_lineedit.text() != "":
            shader_name = self.shader_name_lineedit.text()
        create_shader_args = {"asShader": 1}
        create_sg_args = {"empty": True, "renderable": True, "noSurfaceShader": True}
        if shader_name:
            create_shader_args["name"] = shader_name.title()
            create_sg_args["name"] = shader_name.title() + "_SG"
        shader = cmds.shadingNode("usdPreviewSurface", **create_shader_args)
        shaderSG = cmds.sets(**create_sg_args)
        cmds.connectAttr(shader + ".outColor", shaderSG + ".surfaceShader")

        for key in self.texture_layouts.keys():
            file_path = self.texture_layouts[key].lineedit.text()
            if file_path != "":
                create_tex_args = {"at": True}
                create_place2d_args = {"au": True}
                if shader_name:
                    create_tex_args["name"] = (
                        shader_name.title() + "_" + key.title() + "_file"
                    )
                    create_place2d_args["name"] = (
                        shader_name.title() + "_place2dTexture"
                    )

                file_node = cmds.shadingNode("file", **create_tex_args)
                cmds.setAttr(file_node + ".fileTextureName", file_path, typ="string")
                place2d_node = cmds.shadingNode("place2dTexture", **create_place2d_args)
                cmds.connectAttr(place2d_node + ".outUV", file_node + ".uvCoord")
                if key == "diffuse":
                    cmds.connectAttr(file_node + ".outColor", shader + ".diffuseColor")
                elif key == "emissive":
                    cmds.connectAttr(file_node + ".outColor", shader + ".emissiveColor")
                elif key == "specular":
                    cmds.connectAttr(file_node + ".outColor", shader + ".specularColor")
                elif key == "normal":
                    cmds.connectAttr(file_node + ".outColor", shader + ".normal")
                else:
                    cmds.connectAttr(file_node + ".outColorR", shader + "." + key)
        cmds.select(shader, r=1)
        self.close_widget()


class Texture_Layout(QtWidgets.QHBoxLayout):
    """
    單一貼圖路徑輸入區塊（含檔案選擇與清除）。
    """

    def __init__(self, name, parent=None):
        super(Texture_Layout, self).__init__(parent)
        self.name = name
        self.initUI()

    def initUI(self):
        self.addWidget(QtWidgets.QLabel(self.name.title() + " Texture:"))
        self.lineedit = QtWidgets.QLineEdit()
        # self.lineedit.setReadOnly(True)
        self.file_explorer_btn = QtWidgets.QPushButton("...")
        self.file_explorer_btn.setFixedWidth(16)
        self.addWidget(self.lineedit)
        self.file_erase_btn = QtWidgets.QPushButton("X")
        self.file_erase_btn.setFixedWidth(16)

        self.addWidget(self.file_explorer_btn)
        self.addWidget(self.file_erase_btn)
        self.file_explorer_btn.clicked.connect(self.get_file)
        self.file_erase_btn.clicked.connect(self.file_erase)

    def get_file(self):
        filename = QtWidgets.QFileDialog.getOpenFileName()
        self.lineedit.setText(filename[0])

    def file_erase(self):
        self.lineedit.setText("")


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
        # self.shaderMapMaker(self.shadingGroups)
        self.scope = scope
        # cmds.select(self.root, r=1)
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
                if "/" not in str(path.MakeRelativePath("/")):
                    edit.Add(
                        path,
                        shaders_scope_prim.GetPath().AppendPath(
                            path.MakeRelativePath("/")
                        ),
                    )

        stage.GetRootLayer().Apply(edit)

        edit_dict = {}
        for i in edit.edits:
            edit_dict[i.currentPath] = i.newPath

        for prim in stage.Traverse():
            if prim.GetTypeName() == "Shader":
                shader = UsdShade.Shader.Define(stage, prim.GetPath())
                for i in shader.GetInputs():
                    attr = i.GetAttr()
                    if len(attr.GetConnections()) > 0:
                        print(attr.Get())
                        con = attr.GetConnections()[0]
                        k = con.ReplacePrefix("/", shaders_scope_prim.GetPath())
                        print(k, i.GetFullName(), prim)
                        i.ConnectToSource(k)

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

    def getConnectionNodes(self, node, shadingGroup):
        """
        遞迴取得所有連結的 shader 節點。
        """
        res = cmds.listConnections(node, d=False, c=False, p=False)
        if res:
            for shader in res:
                self.shaderMap[str(shader)] = str(shadingGroup)
                self.getConnectionNodes(shader, shadingGroup)

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


if __name__ == "__main__":

    sel = cmds.ls(sl=True)
    if not sel:
        print("Nothing be selected.")
    else:
        obj = sel[0]
        filenames = cmds.fileDialog2(
            fm=0, startingDirectory=USD_START_DIR, fileFilter=USD_FILE_FILTER
        )

        if filenames:
            filename = filenames[0]
            k = MtoaShadersToUSD(filename, obj)
            k.exportUSD()
