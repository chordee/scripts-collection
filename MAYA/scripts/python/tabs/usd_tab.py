from PySide2 import QtWidgets, QtCore
from maya import cmds

from utils.arnold_to_usd import MtoaShadersToUSD
from utils.materials_assignment import (
    DEFAULT_SCOPE_NAME,
    build_materials_assignment_stage,
)
from utils.usd_attrs import set_usd_type_name
from utils.usd_preview_shader import build_usd_preview_shader


# UI 對話框相關常數
USD_FILE_FILTER = "USD (*.usd *.usda)"
USD_START_DIR = "C:/"


class USD_Tab(QtWidgets.QWidget):
    """
    Maya USD 工具主 UI 標籤頁，提供 SkelRoot、USD Shader、材質匯出等功能。
    """

    def __init__(self, parent=None):
        super(USD_Tab, self).__init__(parent)
        self.initUI()

    def initUI(self):
        self.main_layout = QtWidgets.QHBoxLayout()
        self.setLayout(self.main_layout)
        self.buttons_layout = QtWidgets.QVBoxLayout()
        self.main_layout.addLayout(self.buttons_layout)

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

        self.main_layout.setAlignment(QtCore.Qt.AlignTop)
        self.main_layout.addStretch()

    def create_skelroot_action(self):
        """
        將選取物件加上 SkelRoot 屬性。
        """
        sel = cmds.ls(sl=1, l=1)
        if not sel:
            print("Nothing be selected.")
            return
        set_usd_type_name(sel[0], "SkelRoot")

    def create_usd_preview_shader(self):
        """
        彈出 USD Preview Shader 建立對話框。
        """
        self.preview_shader_dialog = Build_USD_Preview_Shader(self)
        self.preview_shader_dialog.show()

    def export_materials_assignment(
        self,
        scopeName=DEFAULT_SCOPE_NAME,
        purpose="",
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

        stage = build_materials_assignment_stage(
            sel[0],
            scope_name=scopeName,
            purpose=purpose,
            asset_version=assetVersion,
            asset_name=assetName,
        )
        if stage is None:
            print("No shape children found.")
            return

        filenames = cmds.fileDialog2(
            fm=0, startingDirectory=USD_START_DIR, fileFilter=USD_FILE_FILTER
        )
        if not filenames:
            return
        stage.Export(filenames[0])

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
        if not filenames:
            return
        exporter = MtoaShadersToUSD(filenames[0], obj)
        exporter.exportUSD()


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
        從 UI 收集名稱與貼圖路徑，呼叫 utils 建立 USD Preview Shader。
        """
        name = self.shader_name_lineedit.text()
        textures = {
            channel: layout.lineedit.text()
            for channel, layout in self.texture_layouts.items()
            if layout.lineedit.text() != ""
        }
        shader = build_usd_preview_shader(name, textures)
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
