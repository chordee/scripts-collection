# -*- coding: UTF-8 -*_ 

import sys
from PySide2.QtWidgets import *


class MainWindow(QMainWindow):
    def __init__(self):
        QMainWindow.__init__(self)
        self.setAcceptDrops(True)

    def dragEnterEvent(self, e):
        print(type(e))
        mime = e.mimeData()
        print(mime.formats())
        if e.mimeData().hasUrls():
            e.acceptProposedAction()


    def dropEvent(self, e):
        for url in e.mimeData().urls():
            file_name = url.toLocalFile()
            print(url.toString())
            print(e.mimeData().formats())
            print(e.mimeData().text())
            print("Dropped file: " + file_name, url.toString())

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    app.exec_()