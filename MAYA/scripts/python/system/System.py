from PySide2 import QtWidgets, QtGui, QtCore
from maya import cmds


DEFAULT_FONT = "Microsoft YaHei Mono"


class System_Tab(QtWidgets.QWidget):
    """
    Maya 系統工具主 UI 標籤頁，提供 Script Editor 字型、Parent Shape、Reference 匯入、Namespace 移除等功能。
    """

    def __init__(self, parent=None):
        super(System_Tab, self).__init__(parent)
        self.initUI()

    def initUI(self):
        self.layout = QtWidgets.QHBoxLayout()
        self.setLayout(self.layout)
        self.buttons_layout = QtWidgets.QVBoxLayout()
        self.layout.addLayout(self.buttons_layout)
        self.fontstyle_dialog = FontStyle_Dialog(self)

        # buttons_layout
        self.change_script_editor_font_style_btn = QtWidgets.QPushButton(
            "Change Script Editor Font Style"
        )
        self.parent_shape_btn = QtWidgets.QPushButton("Parent Shape")
        self.import_all_refs_btn = QtWidgets.QPushButton("Import All References")
        self.remove_all_namespace_btn = QtWidgets.QPushButton("Remove All Namespaces")

        self.buttons_layout.addWidget(self.change_script_editor_font_style_btn)
        self.buttons_layout.addWidget(self.parent_shape_btn)
        self.buttons_layout.addWidget(self.import_all_refs_btn)
        self.buttons_layout.addWidget(self.remove_all_namespace_btn)

        self.change_script_editor_font_style_btn.clicked.connect(
            self.change_script_editor_font_style
        )
        self.parent_shape_btn.clicked.connect(self.parent_shape)
        self.import_all_refs_btn.clicked.connect(self.import_all_refs)
        self.remove_all_namespace_btn.clicked.connect(self.remove_all_namespaces)

        self.layout.setAlignment(QtCore.Qt.AlignTop)
        self.layout.addStretch()

    def change_script_editor_font_style(self):
        """
        顯示 Script Editor 字型調整對話框。
        """
        self.fontstyle_dialog.show()

    def parent_shape(self):
        """
        將第一個選取物件的 shape parent 到第二個物件。
        """
        sels = cmds.ls(sl=1, l=1)
        if not sels or len(sels) < 2:
            QtWidgets.QMessageBox.warning(
                self, "Parent Shape", "請選取兩個物件（先選 shape，後選 parent）"
            )
            return
        shapes = cmds.listRelatives(sels[0], s=True)
        if not shapes:
            QtWidgets.QMessageBox.warning(self, "Parent Shape", "第一個物件沒有 shape")
            return
        shape = shapes[0]
        try:
            cmds.parent(shape, sels[1], r=True, s=True)
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "Parent Shape", f"Parent 失敗: {e}")

    def import_all_refs(self):
        """
        匯入所有 reference，最多 100 次迴圈防止無窮迴圈。
        """
        loop_count = 0
        while len(cmds.file(q=1, r=1)) > 0:
            for f in cmds.file(q=1, r=1):
                try:
                    cmds.file(f, importReference=True)
                except Exception as e:
                    QtWidgets.QMessageBox.warning(
                        self, "Import All References", f"匯入 reference 失敗: {e}"
                    )
            loop_count += 1
            if loop_count > 100:
                QtWidgets.QMessageBox.warning(
                    self,
                    "Import All References",
                    "Reference 匯入超過 100 次，可能有壞掉的 reference。",
                )
                break

    def remove_all_namespaces(self):
        """
        移除所有非 shared/UI 的 namespace。
        """
        namespaces = cmds.namespaceInfo(listOnlyNamespaces=True, recurse=True)
        if not namespaces:
            QtWidgets.QMessageBox.information(
                self, "Remove All Namespaces", "沒有可移除的 namespace。"
            )
            return
        for ns in namespaces:
            if ns != "shared" and ns != "UI":
                try:
                    cmds.namespace(set=":")
                    cmds.namespace(rm=ns, mnr=1)
                except Exception as e:
                    QtWidgets.QMessageBox.warning(
                        self, "Remove All Namespaces", f"移除 {ns} 失敗: {e}"
                    )


class FontStyle_Dialog(QtWidgets.QDialog):
    """
    Script Editor 字型調整對話框。
    """

    def __init__(self, parent):
        super(FontStyle_Dialog, self).__init__(parent)
        self.initUI()

    def initUI(self):
        self.setWindowTitle("Change Font Style")
        main_layout = QtWidgets.QVBoxLayout()
        font_style_layout = QtWidgets.QHBoxLayout()
        font_size_layout = QtWidgets.QHBoxLayout()
        btns_layout = QtWidgets.QHBoxLayout()
        self.ok_btn = QtWidgets.QPushButton("OK")
        self.cancel_btn = QtWidgets.QPushButton("Cancel")

        font_style_label = QtWidgets.QLabel("Font:")
        self.font_style_lineedit = QtWidgets.QLineEdit()
        self.font_style_lineedit.setText(DEFAULT_FONT)
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
            lambda: self.font_size_spinbox.setValue(self.font_size_slider.value())
        )
        self.font_size_spinbox.valueChanged.connect(
            lambda: self.font_size_slider.setValue(self.font_size_spinbox.value())
        )

        self.ok_btn.clicked.connect(self.change_font)
        self.cancel_btn.clicked.connect(self.close_dialog)

    def change_font(self):
        """
        變更 Script Editor 字型與大小，支援不同 Maya 版本。
        """
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
            style = """
                QPlainTextEdit {
                    font-family: %s;
                    font: normal %dpx;
                }
                """ % (
                font,
                size,
            )
            win.setStyleSheet(style)

        # for Maya 2020 and older
        else:
            style = """
                QWidget[maya_ui="scriptEditor"] QTextEdit {
                    font-family: %s;
                    font: normal %dpx;
                }
                """ % (
                font,
                size,
            )
            win.setProperty("maya_ui", "scriptEditor")
            app.setStyleSheet(style)
        self.close_dialog()

    def close_dialog(self):
        """
        關閉對話框。
        """
        self.close()
