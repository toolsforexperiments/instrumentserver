import sys
from qtpy import QtGui, QtCore, QtWidgets
from PyQt5.QtCore import Qt, QRect
import GUIpackage as GP
from pkg import hatWidgets as hW

GenList = ["Gen0", "Gen1", "Gen2", "Gen3"]


class UI_Gens(object):
    def __init__(self, win_, GenList):
        self.GenList = GenList
        self.pixelY = 1080
        self.ratio = 16/9
        self.pixelX = self.pixelY * self.ratio
        self._translate = QtCore.QCoreApplication.translate
        self.win_ = win_
        self.win_.resize(self.pixelX, self.pixelY)
        self.win_.setWindowTitle(self._translate("Dialog", "Instruments"))

    def setupUI(self):
        leftPixel = self.pixelX * 0.55
        self.frameGen = QtWidgets.QFrame(self.win_)
        self.frameGen.setGeometry(QtCore.QRect(10, 10, leftPixel, self.pixelY*0.5))
        self.frameGen.setFrameShape(QtWidgets.QFrame.Box)
        self.frameGen.setFrameShadow(QtWidgets.QFrame.Raised)
        self.frameGen.setLineWidth(5)

        self.frameCS = QtWidgets.QFrame(self.win_)
        self.frameCS.setGeometry(QtCore.QRect(10, self.pixelY*0.5 + 20, leftPixel, self.pixelY*0.2))
        self.frameCS.setFrameShape(QtWidgets.QFrame.Box)
        self.frameCS.setFrameShadow(QtWidgets.QFrame.Raised)
        self.frameCS.setLineWidth(5)

        self.frameSWT = QtWidgets.QFrame(self.win_)
        self.frameSWT.setGeometry(QtCore.QRect(10, self.pixelY*0.7 + 30, leftPixel, self.pixelY*0.3 - 100))
        self.frameSWT.setFrameShape(QtWidgets.QFrame.Box)
        self.frameSWT.setFrameShadow(QtWidgets.QFrame.Raised)
        self.frameSWT.setLineWidth(5)

        self.frameAllOther = QtWidgets.QFrame(self.win_)
        self.frameAllOther.setGeometry(QtCore.QRect(leftPixel + 10, 10, self.pixelX - leftPixel - 20, self.pixelY*0.8))
        self.frameAllOther.setFrameShape(QtWidgets.QFrame.Box)
        self.frameAllOther.setFrameShadow(QtWidgets.QFrame.Raised)
        self.frameAllOther.setLineWidth(5)
        

        # genGridLayoutWidget = hW.gridLayoutWithTitle(self.frameGen)
        # genGridLayout = genGridLayoutWidget.gridLayout()
        # genGridLayoutWidget.title('Generators')
        '''
        genGridLayoutWidget = QtWidgets.QWidget(self.frameGen)
        genGridLayout = QtWidgets.QGridLayout(genGridLayoutWidget)
        genGridLayout.setContentsMargins(0, 0, 0, 0)
        genGridLayout.setHorizontalSpacing(10)
        genGridLayout.setVerticalSpacing(10)

        genTitle = QtWidgets.QLabel(genGridLayoutWidget)
        genTitle.setFont(GP.fontFunc('Arial', 20, weight=70))
        genTitle.setText(self._translate("Dialog", "Generators"))
        genTitle.setWordWrap(True)
        genTitle.setFixedHeight(30)
        genGridLayout.addWidget(genTitle, 0, 0, 1, 13, alignment=Qt.AlignHCenter)

        centralwidget = QtWidgets.QWidget(self.frameGen)
        centralwidget.setGeometry(QtCore.QRect(20, 20, leftPixel - 40, self.pixelY * 0.5 - 40))

        scroll = QtWidgets.QScrollArea(centralwidget)
        scroll.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOn)
        scroll.setWidgetResizable(True)
        scroll.setFixedHeight(int(self.pixelY * 0.5 - 100))
        scroll.setFixedWidth(leftPixel - 40)
        scroll.setWidget(genGridLayoutWidget)


        controlList = ["Name", "On/Off", "Freq(GHz)", "Power(dBm)", "Fase(degree)", "Ref (ext/int)", "Control"]
        for i in range(len(controlList)):
            self.label = QtWidgets.QLabel(genGridLayoutWidget)
            self.label.setFont(GP.fontFunc('Arial', 10, weight=70))
            self.label.setText(self._translate("Dialog", controlList[i]))
            self.label.setWordWrap(True)
            self.label.setFixedHeight(20)
            genGridLayout.addWidget(self.label, 1, 2*i, 1, 2, alignment=Qt.AlignHCenter)

        for j in range(len(self.GenList)):
            self.label = QtWidgets.QLabel(genGridLayoutWidget)
            self.label.setFont(GP.fontFunc('Arial', 10, weight=70))
            self.label.setText(self._translate("Dialog", self.GenList[j]))
            genGridLayout.addWidget(self.label, j + 2, 0, 1, 2)

            switch = hW.SwitchOnOff()
            switch.setChecked(False)
            genGridLayout.addWidget(switch, j + 2, 2, 1, 2)

            for k in range(4):
                self.label = QtWidgets.QLabel(genGridLayoutWidget)
                self.label.setFont(GP.fontFunc('Arial', 8, weight=50))
                self.label.setText(self._translate("Dialog", "XXX"))
                genGridLayout.addWidget(self.label, j + 2, 2 * k + 4, 1, 1)

                self.lineEdit = QtWidgets.QLineEdit(genGridLayoutWidget)
                self.lineEdit.setClearButtonEnabled(True)
                self.lineEdit.setFont(GP.fontFunc('Arial', 10))
                self.lineEdit.setText(self._translate("Dialog", "XXX"))
                genGridLayout.addWidget(self.lineEdit, j + 2, 2 * k + 5, 1, 1)


            self.pushButton = QtWidgets.QPushButton(genGridLayoutWidget)
            genGridLayout.addWidget(self.pushButton, j + 2, 11+1, 1, 1)
            self.pushButton.setText(self._translate("Dialog", "Get"))

            self.pushButton = QtWidgets.QPushButton(genGridLayoutWidget)
            genGridLayout.addWidget(self.pushButton, j + 2, 11+2, 1, 1)
            self.pushButton.setText(self._translate("Dialog", "Set"))

        self.listView = QtWidgets.QListView(self.frameGen)
        self.listView.setGeometry(QtCore.QRect(1100, 50, 300, 600))
        '''

if __name__ == '__main__':
    app = QtWidgets.QApplication(sys.argv)
    Dialog = QtWidgets.QDialog()
    ui = UI_Gens(Dialog, GenList)
    ui.setupUI()
    Dialog.show()
    sys.exit(app.exec_())
