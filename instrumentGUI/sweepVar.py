import sys
from qtpy import QtGui, QtCore, QtWidgets
from PyQt5.QtCore import Qt, QRect
import GUIpackage as GP
from pkg import hatWidgets as hW
from pkg import hatCore as hC
import time
import h5py

from matplotlib.backends.backend_qt5agg import (
    FigureCanvas, NavigationToolbar2QT as NavigationToolbar)
from matplotlib.figure import Figure
import numpy as np
from plotWindow import ApplicationWindow

defaultList = {'VNA': {'IFBW': '3000', 'Avg': True}, 'Current Source': {'rampMode': True}}
parameterList = {'VNA': {'freqStart': '4e9', 'freqEnd': '5e9', 'sweepPoints': '1601', 'RFPower': '-70', 'AvgNum': '10'}, 'Current Source': {'Range': '10'}}
sweepVar = {'Current Source': {'current': {'start': '1', 'end': '10', 'step': '0.01'}}}


class UI_sweepVar(object):
    def __init__(self, win_, GenList):
        self.GenList = GenList
        self.pixelY = 1080
        self.ratio = 16/9
        self.pixelX = self.pixelY * self.ratio
        self._translate = QtCore.QCoreApplication.translate
        self.win_ = win_
        self.win_.resize(self.pixelX, self.pixelY)
        self.win_.setWindowTitle(self._translate("GUI", "Instruments"))

    def setupUI(self):
        tabWidget = QtWidgets.QTabWidget(self.win_)
        tabWidget.setGeometry(QtCore.QRect(20, 100, self.pixelX * 0.4, 200))
        
        for key in defaultList.keys():
            tab = QtWidgets.QWidget()
            widget = QtWidgets.QWidget(tab)
            widget.setGeometry(QtCore.QRect(0, 0, self.pixelX * 0.4, 170))
            gridLayout = hW.comboLabelTextWithScroll(widget, defaultList[key], titles=['Var', 'Value'])
            tabWidget.addTab(tab, key)

        tabWidget = QtWidgets.QTabWidget(self.win_)
        tabWidget.setGeometry(QtCore.QRect(20, 350, self.pixelX * 0.4, 300))
        for key in parameterList.keys():
            tab = QtWidgets.QWidget()
            widget = QtWidgets.QWidget(tab)
            widget.setGeometry(QtCore.QRect(0, 0, self.pixelX * 0.4, 270))
            gridLayout = hW.comboLabelLineEditWithScroll(widget, parameterList[key], titles=['Var', 'Value'])
            tabWidget.addTab(tab, key)

        frameSweep = QtWidgets.QFrame(self.win_)
        frameSweep.setGeometry(QtCore.QRect(20, 700, self.pixelX * 0.4, 300))
        frameSweep.setFrameShape(QtWidgets.QFrame.Box)
        frameSweep.setFrameShadow(QtWidgets.QFrame.Raised)
        frameSweep.setLineWidth(5)

        controlWidget = QtWidgets.QWidget(frameSweep)
        controlWidget.setGeometry(QtCore.QRect(20, 20, self.pixelX * 0.4 * 0.9, 50))
        HBox = QtWidgets.QHBoxLayout(controlWidget)
        HBox.setContentsMargins(0, 0, 0, 0)
        titleList = ['instr', 'var', 'start', 'end', 'step']
        for i in range(5):
            label = QtWidgets.QLabel(widget)
            if i == 0:
                label.setFixedWidth(200)
            else:
                label.setFixedWidth(100)
            label.setFont(hC.fontFunc('Arial', 15, weight=75))
            label.setText(self._translate("GUI", titleList[i]))
            HBox.addWidget(label)

        gridLayoutWidget = QtWidgets.QWidget(frameSweep)
        gridLayoutWidget.setGeometry(QtCore.QRect(20, 100, self.pixelX * 0.4 * 0.9, 180))
        gridLayout = QtWidgets.QGridLayout(gridLayoutWidget)
        gridLayout.setContentsMargins(0, 0, 0, 0)
        gridLayout.setHorizontalSpacing(10)
        gridLayout.setVerticalSpacing(10)

        index = 0
        for key in sweepVar.keys():
            labelKey = QtWidgets.QLabel(widget)
            labelKey.setFont(hC.fontFunc('Arial', 12))
            labelKey.setText(self._translate("GUI", key))
            labelKey.setFixedWidth(200)
            gridLayout.addWidget(labelKey, index, 0, 1, 1)
            for var in sweepVar[key].keys():
                labelVar = QtWidgets.QLabel(widget)
                labelVar.setFont(hC.fontFunc('Arial', 12))
                labelVar.setText(self._translate("GUI", var))
                labelVar.setFixedWidth(100)
                gridLayout.addWidget(labelVar, index, 1, 1, 1)
                sweepList = [sweepVar[key][var]['start'], sweepVar[key][var]['end'], sweepVar[key][var]['step']]
                for i in range(3):
                    lineEdit = QtWidgets.QLineEdit(widget)
                    lineEdit.setClearButtonEnabled(True)
                    lineEdit.setFont(hC.fontFunc('Arial', 12))
                    lineEdit.setText(self._translate("GUI", sweepList[i]))
                    lineEdit.setFixedWidth(100)
                    gridLayout.addWidget(lineEdit, index, i + 2 , 1, 1)       
                index += 1

        pushButtonLoad = QtWidgets.QPushButton(self.win_)
        pushButtonLoad.setText(self._translate("Dialog", "Load"))
        pushButtonMsmt = QtWidgets.QPushButton(self.win_)
        pushButtonMsmt.setText(self._translate("Dialog", "Measure"))

        buttonWidget = QtWidgets.QWidget(self.win_)
        buttonWidget.setGeometry(QtCore.QRect(self.pixelX * 0.5 + 200, 100, 400, 100))
        HBox = QtWidgets.QHBoxLayout(buttonWidget)
        HBox.setContentsMargins(0, 0, 0, 0)
        HBox.addWidget(pushButtonLoad)
        HBox.addWidget(pushButtonMsmt)

        progressBar = QtWidgets.QProgressBar(Dialog)
        progressBar.setGeometry(QtCore.QRect(self.pixelX * 0.5 + 20, 300, 800, 50))
        progressBar.setFont(hC.fontFunc('Arial', 16))
        progressBar.setProperty("value", 100)

        class plotThread(QtCore.QThread):
            def __init__(self):
                QtCore.QThread.__init__(self)
            def __del__(self):
                self.wait()
            def run(self):
                app = ApplicationWindow()
                app.show()
                app.activateWindow()
                app.raise_()
                app.exec_

        def measurementPro():
            # plotFunc = plotThread()
            # plotFunc.start()

            fileSave = h5py.File('test', 'w')
            dataList = []
            rawSave = fileSave.create_dataset('rawData', data=np.array(dataList))
            for i in range(5):
                progressBar.setProperty('value', i+1)
                time.sleep(0.1)
                dataList.append(np.random.rand(50))
                fileSave['rawData'][...] = np.array(dataList)
            fileSave.close()
        pushButtonMsmt.clicked.connect(measurementPro)


if __name__ == '__main__':
    app = QtWidgets.QApplication(sys.argv)
    Dialog = QtWidgets.QDialog()
    ui = UI_sweepVar(Dialog, defaultList)
    ui.setupUI()
    Dialog.show()
    sys.exit(app.exec_())
