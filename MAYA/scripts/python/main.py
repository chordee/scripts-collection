from maya import OpenMayaUI as omui
from tabs.usd_tab import USD_Tab
from tabs.system_tab import System_Tab

from PySide2 import QtWidgets, QtGui, QtCore
from shiboken2 import wrapInstance


class MainWin(QtWidgets.QMainWindow):
    def __init__(self, parent):
        super(MainWin, self).__init__(parent=parent)
        self.initUI()

    def initUI(self):
        self.main_widget = MainWidget(self)
        self.setCentralWidget(self.main_widget)
        self.resize(800, 600)
        self.setWindowTitle('Tools')


class MainWidget(QtWidgets.QWidget):
    def __init__(self, parent):
        super(MainWidget, self).__init__(parent)
        self.initUI()

    def initUI(self):
        self.main_layout = QtWidgets.QVBoxLayout(self)
        self.tabs = QtWidgets.QTabWidget()

        # System tab
        self.system_tab = System_Tab(self)
        self.tabs.addTab(self.system_tab, 'System')

        # USD tab
        self.usd_tab = USD_Tab(self)
        self.tabs.addTab(self.usd_tab, 'USD')

        # Shader tab
        self.shader_tab = QtWidgets.QWidget()
        self.tabs.addTab(self.shader_tab, 'Shader')
        self.shader_tab.layout = QtWidgets.QVBoxLayout()
        self.shader_tab.setLayout(self.shader_tab.layout)

        self.main_layout.addWidget(self.tabs)
        self.setLayout(self.main_layout)


if __name__ == '__main__':
    mayaMainWindowPtr = omui.MQtUtil.mainWindow()
    mayaMainWindow = wrapInstance(int(mayaMainWindowPtr), QtWidgets.QWidget)

    for widget in QtWidgets.QApplication.instance().topLevelWidgets():
        if widget.objectName() == 'chd_tools_main_window':
            widget.close()
            break

    main_window = MainWin(parent=mayaMainWindow)
    main_window.setObjectName('chd_tools_main_window')
    main_window.show()
