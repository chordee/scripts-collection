# -*- coding: UTF-8 -*_ 

import sys, os
from PySide2 import QtWidgets

FFMPEG = 'Q:\\Resource\\houdini_modules\\ffmpeg\\bin\\ffmpeg.exe'

class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super(MainWindow, self).__init__()
        self.setAcceptDrops(True)

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()


    def dropEvent(self, e):
        for url in e.mimeData().urls():
            file_name = url.toLocalFile()
            if file_name.split('.')[-1] == 'mp4':
                export_file_name = '.'.join(file_name.split('.')[:-1]) + '.fixed.mp4'
                cmd = [FFMPEG, '-i', '"' + file_name.replace('/', '\\') + '"', '-vf', '"colorspace=all=bt709:trc=srgb:range=pc"', '"' + export_file_name + '"']
                os.system(' '.join(cmd))

if __name__ == '__main__':
    app = QtWidgets.QApplication(sys.argv)
    window = MainWindow()
    window.show()
    app.exec_()