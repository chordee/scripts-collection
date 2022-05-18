from PySide2 import QtWidgets, QtGui, QtCore
from maya import cmds


class System_Tab(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super(System_Tab, self).__init__(parent)
        self.initUI()

    def initUI(self):
        self.layout = QtWidgets.QHBoxLayout()
        self.setLayout(self.layout)
        self.buttons_layout = QtWidgets.QVBoxLayout()
        self.layout.addLayout(self.buttons_layout)
        self.fontsytle_dialog = FontStyle_Dialog(self)

        # buttons_layout
        self.change_script_editor_font_style_btn = QtWidgets.QPushButton(
            'Change Script Editor Font Style')
        self.buttons_layout.addWidget(self.change_script_editor_font_style_btn)
        self.change_script_editor_font_style_btn.clicked.connect(
            self.change_script_editor_font_style)
        self.layout.setAlignment(QtCore.Qt.AlignTop)
        self.layout.addStretch()

    def change_script_editor_font_style(self):
        self.fontsytle_dialog.show()


class FontStyle_Dialog(QtWidgets.QDialog):
    def __init__(self, parent):
        super(FontStyle_Dialog, self).__init__(parent)
        self.initUI()

    def initUI(self):
        self.setWindowTitle('Change Font Style')
        main_layout = QtWidgets.QVBoxLayout()
        font_style_layout = QtWidgets.QHBoxLayout()
        font_size_layout = QtWidgets.QHBoxLayout()
        btns_layout = QtWidgets.QHBoxLayout()
        self.ok_btn = QtWidgets.QPushButton('OK')
        self.cancel_btn = QtWidgets.QPushButton('Cancel')

        font_style_label = QtWidgets.QLabel('Font:')
        self.font_style_lineedit = QtWidgets.QLineEdit()
        self.font_style_lineedit.setText('Microsoft YaHei Mono')
        font_style_layout.addWidget(font_style_label)
        font_style_layout.addWidget(self.font_style_lineedit)

        min = 6
        max = 20
        single_step = 1
        default_size = 12
        self.font_size_slider = QtWidgets.QSlider()
        self.font_size_slider.setOrientation(QtCore.Qt.Horizontal)
        self.font_size_slider.setMinimum(min)
        self.font_size_slider.setMaximum(max)
        self.font_size_slider.setSingleStep(single_step)
        self.font_size_slider.setValue(default_size)
        self.font_size_spinbox = QtWidgets.QSpinBox()
        self.font_size_spinbox.setMinimum(min)
        self.font_size_spinbox.setMaximum(max)
        self.font_size_spinbox.setSingleStep(single_step)
        self.font_size_spinbox.setValue(default_size)
        font_size_layout.addWidget(self.font_size_spinbox)
        font_size_layout.addWidget(self.font_size_slider)

        btns_layout.addWidget(self.ok_btn)
        btns_layout.addWidget(self.cancel_btn)

        main_layout.addLayout(font_style_layout)
        main_layout.addLayout(font_size_layout)
        main_layout.addLayout(btns_layout)

        self.setLayout(main_layout)

        self.font_size_slider.valueChanged.connect(
            lambda: self.font_size_spinbox.setValue(self.font_size_slider.value()))
        self.font_size_spinbox.valueChanged.connect(
            lambda: self.font_size_slider.setValue(self.font_size_spinbox.value()))

        self.ok_btn.clicked.connect(self.change_font)
        self.cancel_btn.clicked.connect(self.close_dialog)

    def change_font(self):
        font = self.font_style_lineedit.text()
        size = self.font_size_spinbox.value()
        app = QtWidgets.QApplication.instance()
        win = None
        for w in app.topLevelWidgets():
            if "Script Editor" in w.windowTitle():
                win = w
                break

        if win is None:
            return

        # for Maya 2022 and above
        if int(cmds.about(version=True)) >= 2022:
            style = '''
                QPlainTextEdit {
                    font-family: %s;
                    font: normal %dpx;
                }
                ''' % (font, size)
            win.setStyleSheet(style)

        # for Maya 2020 and older
        else:
            style = '''
                QWidget[maya_ui="scriptEditor"] QTextEdit {
                    font-family: %s;
                    font: normal %dpx;
                }
                ''' % (font, size)
            win.setProperty('maya_ui', 'scriptEditor')
            app.setStyleSheet(style)
        self.close_dialog()

    def close_dialog(self):
        self.close()
