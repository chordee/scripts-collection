
from PySide2 import QtWidgets, QtGui, QtCore
from maya import cmds


class USD_Tab(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super(USD_Tab, self).__init__(parent)
        self.initUI()

    def initUI(self):
        self.layout = QtWidgets.QHBoxLayout()
        self.setLayout(self.layout)
        self.buttons_layout = QtWidgets.QVBoxLayout()
        self.layout.addLayout(self.buttons_layout)

        # buttons_layout
        self.create_skelroot_btn = QtWidgets.QPushButton(
            'Create SkelRoot Attribute')
        self.crate_usd_preview_shader_btn = QtWidgets.QPushButton(
            'Build USD Preview Sahder')
        self.buttons_layout.addWidget(self.create_skelroot_btn)
        self.buttons_layout.addWidget(self.crate_usd_preview_shader_btn)
        self.create_skelroot_btn.clicked.connect(self.create_skelroot_action)
        self.crate_usd_preview_shader_btn.clicked.connect(
            self.create_usd_preview_shader)
        self.layout.setAlignment(QtCore.Qt.AlignTop)
        self.layout.addStretch()

    def create_skelroot_action(self):
        try:
            obj = cmds.ls(sl=1, l=1)[0]
            cmds.addAttr(obj, ln='USD_typeName', dt='string')
            cmds.setAttr(obj + '.USD_typeName', 'SkelRoot', typ='string')
        except IndexError:
            print("Nothing be selected.")

    def create_usd_preview_shader(self):
        dialog = Build_USD_Preview_Shader(self)
        dialog.show()


class Build_USD_Preview_Shader(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super(Build_USD_Preview_Shader, self).__init__(parent)
        self.initUI()

    def initUI(self):
        self.setWindowTitle('Build USD Preview Shader')
        main_layout = QtWidgets.QVBoxLayout()
        btn_layout = QtWidgets.QHBoxLayout()
        main_layout.setSpacing(2)

        # Name horizontal layout
        name_layout = QtWidgets.QHBoxLayout()
        name_layout.addWidget(QtWidgets.QLabel('Name:'))
        self.shader_name_lineedit = QtWidgets.QLineEdit()
        name_layout.addWidget(self.shader_name_lineedit)
        main_layout.addLayout(name_layout)

        # Textures layout
        textures_list = ['diffuse', 'emissive', 'occlusion', 'opacity', 'ior',
                         'metallic', 'roughness', 'specular', 'normal', 'displacement']

        self.texture_layouts = dict()
        for n in textures_list:
            self.texture_layouts[n] = Texture_Layout(n)
            main_layout.addLayout(self.texture_layouts[n])

        # Buttons Layout
        self.create_btn = QtWidgets.QPushButton("Create")
        self.cancel_btn = QtWidgets.QPushButton('Cancel')
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
        shader_name = None
        if self.shader_name_lineedit.text() != '':
            shader_name = self.shader_name_lineedit.text()
        craete_shader_args = {'asShader': 1}
        create_sg_args = {'empty': True,
                          'renderable': True, 'noSurfaceShader': True}
        if shader_name:
            craete_shader_args['name'] = shader_name.title()
            create_sg_args['name'] = shader_name.title() + '_SG'
        shader = cmds.shadingNode('usdPreviewSurface', **craete_shader_args)
        shaderSG = cmds.sets(**create_sg_args)
        cmds.connectAttr(shader + '.outColor', shaderSG + '.surfaceShader')

        for key in self.texture_layouts.keys():
            file_path = self.texture_layouts[key].lineedit.text()
            if file_path != '':
                create_tex_args = {'at': True}
                create_place2d_args = {'au': True}
                if shader_name:
                    create_tex_args['name'] = shader_name.title() + \
                        '_' + key.title() + '_file'
                    create_place2d_args['name'] = shader_name.title(
                    ) + '_place2dTexture'

                file_node = cmds.shadingNode('file', **create_tex_args)
                cmds.setAttr(file_node + '.fileTextureName',
                             file_path, typ='string')
                place2d_node = cmds.shadingNode(
                    'place2dTexture', **create_place2d_args)
                cmds.connectAttr(place2d_node + '.outUV',
                                 file_node + '.uvCoord')
                if key == 'diffuse':
                    cmds.connectAttr(file_node + '.outColor',
                                     shader + '.diffuseColor')
                elif key == 'emissive':
                    cmds.connectAttr(file_node + '.outColor',
                                     shader + '.emissiveColor')
                elif key == 'specular':
                    cmds.connectAttr(file_node + '.outColor',
                                     shader + '.specularColor')
                elif key == 'normal':
                    cmds.connectAttr(file_node + '.outColor',
                                     shader + '.normal')
                else:
                    cmds.connectAttr(file_node + '.outColorR',
                                     shader + '.' + key)
        cmds.select(shader, r=1)
        self.close_widget()


class Texture_Layout(QtWidgets.QHBoxLayout):
    def __init__(self, name, parent=None):
        super(Texture_Layout, self).__init__(parent)
        self.name = name
        self.initUI()

    def initUI(self):
        self.addWidget(QtWidgets.QLabel(
            self.name.title() + ' Texture:'))
        self.lineedit = QtWidgets.QLineEdit()
        # self.lineedit.setReadOnly(True)
        self.file_explorer_btn = QtWidgets.QPushButton('...')
        self.file_explorer_btn.setFixedWidth(16)
        self.addWidget(self.lineedit)
        self.file_erase_btn = QtWidgets.QPushButton('X')
        self.file_erase_btn.setFixedWidth(16)

        self.addWidget(self.file_explorer_btn)
        self.addWidget(self.file_erase_btn)
        self.file_explorer_btn.clicked.connect(self.get_file)
        self.file_erase_btn.clicked.connect(self.file_erase)

    def get_file(self):
        filename = QtWidgets.QFileDialog.getOpenFileName()
        self.lineedit.setText(filename[0])

    def file_erase(self):
        self.lineedit.setText('')
