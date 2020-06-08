import sys
sys.path.append(r'D:\\pythonLocal\\instrumentserver\\')
import logging
from pprint import pprint

from qcodes import Instrument

from instrumentserver.server import *
from instrumentserver.server.core import InstrumentCreationSpec
from instrumentserver.client import *
from instrumentserver import log

from qtpy import QtGui, QtCore, QtWidgets
from PyQt5.QtCore import Qt, QRect
import GUIpackage as GP
from pkg import hatWidgets as hW



class UI_test(object):
    def __init__(self, win_):
        self.pixelY = 1080
        self.ratio = 16/9
        self.pixelX = self.pixelY * self.ratio
        self._translate = QtCore.QCoreApplication.translate
        self.win_ = win_
        self.win_.resize(self.pixelX, self.pixelY)
        self.win_.setWindowTitle(self._translate("Dialog", "Instruments"))

    def setupUI(self):
        instrPar = hW.widgetInstrumentTabParametersTree(self.win_)
        instrPar.pos(10, 10, self.pixelX*0.4, self.pixelY*0.5)
        instrPar.processClient(instrDict)
        instrPar.checkSubModule()
        instrPar.modelTab()
        instrPar.instrTreeParent()
        instrPar.instrParChild()

        pushButtonGet = QtWidgets.QPushButton(self.win_)
        pushButtonGet.setText('Get')
        pushButtonGet.clicked.connect(instrPar.getPar)
        pushButtonSet = QtWidgets.QPushButton(self.win_)
        pushButtonSet.setText('Set')
        pushButtonSet.clicked.connect(instrPar.setPar)

        buttonWidget = QtWidgets.QWidget(self.win_)
        buttonWidget.setGeometry(QtCore.QRect(10, self.pixelY*0.6, 400, 100))
        HBox = QtWidgets.QHBoxLayout(buttonWidget)
        HBox.setContentsMargins(0, 0, 0, 0)
        HBox.addWidget(pushButtonGet)
        HBox.addWidget(pushButtonSet)

if __name__ == '__main__':
    with Client() as cli:
        pprint(cli.list_instruments())
        instrDict = {}
        for key in cli.list_instruments():
            instrDict[key] = cli.get_instrument(key)

        app = QtWidgets.QApplication(sys.argv)
        Dialog = QtWidgets.QDialog()
        ui = UI_test(Dialog)
        ui.setupUI()
        Dialog.show()
        sys.exit(app.exec_())
