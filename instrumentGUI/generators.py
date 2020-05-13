import sys
from qtpy import QtGui, QtCore, QtWidgets
import GUIpackage as GP

GenList = ["Gen0", "Gen1"]#, "Gen2", "Gen3"]

class UI_Gens(object):
    def __init__(self, win_, GenList):
        self._translate = QtCore.QCoreApplication.translate
        self.GenList = GenList
        self.win_ = win_
        self.win_.setObjectName("Logging")
        self.win_.resize(1920, 1080)
        self.win_.setWindowTitle(self._translate("MainWindow", "Hat Logging"))

    def setupUI(self):
        self.frame = QtWidgets.QFrame(self.win_)
        self.frame.setGeometry(QtCore.QRect(10, 10, 1440, 810))
        self.frame.setFrameShape(QtWidgets.QFrame.Box)
        self.frame.setFrameShadow(QtWidgets.QFrame.Raised)
        self.frame.setLineWidth(5)

        self.gridLayoutWidget = QtWidgets.QWidget(self.frame)
        self.gridLayoutWidget.setGeometry(QtCore.QRect(20, 20, 1000, 300))
        self.gridLayout = QtWidgets.QGridLayout(self.gridLayoutWidget)
        self.gridLayout.setContentsMargins(0, 0, 0, 0)
        self.gridLayout.setHorizontalSpacing(20)
        self.gridLayout.setVerticalSpacing(10)

        controlList = ["Name", "On/Off", "Frequency(GHz)", "Power(dBm)", "Fase(degree)", "Reference \n(ext/int)", "Control"]
        for i in range(len(controlList)):
            self.label = QtWidgets.QLabel(self.gridLayoutWidget)
            self.label.setFont(GP.fontFunc('Arial', 10, weight=70))
            self.label.setText(self._translate("Dialog", controlList[i]))
            self.label.setWordWrap(True)
            self.gridLayout.addWidget(self.label, 0, 2*i, 1, 2)

        for j in range(len(GenList)):
            self.label = QtWidgets.QLabel(self.gridLayoutWidget)
            self.label.setFont(GP.fontFunc('Arial', 10, weight=70))
            self.label.setText(self._translate("Dialog", GenList[j]))
            self.gridLayout.addWidget(self.label, j + 2, 0, 1, 2)

            self.radioButton = QtWidgets.QRadioButton(self.gridLayoutWidget)
            self.gridLayout.addWidget(self.radioButton, j + 2, 2, 1, 2)
            self.radioButton.setText(self._translate("MainWindow", "RF out"))

            for k in range(4):
                self.label = QtWidgets.QLabel(self.gridLayoutWidget)
                self.label.setFont(GP.fontFunc('Arial', 8, weight=50))
                self.label.setText(self._translate("Dialog", "XXX"))
                self.gridLayout.addWidget(self.label, j + 2, 2 * k + 4, 1, 1)

                self.lineEdit = QtWidgets.QLineEdit(self.gridLayoutWidget)
                self.lineEdit.setClearButtonEnabled(True)
                self.lineEdit.setFont(GP.fontFunc('Arial', 10))
                self.lineEdit.setText(self._translate("Dialog", "XXX"))
                self.gridLayout.addWidget(self.lineEdit, j + 2, 2 * k + 5, 1, 1)


            self.pushButton = QtWidgets.QPushButton(self.gridLayoutWidget)
            self.gridLayout.addWidget(self.pushButton, j + 2, 11+1, 1, 1)
            self.pushButton.setText(self._translate("Dialog", "Get"))

            self.pushButton = QtWidgets.QPushButton(self.gridLayoutWidget)
            self.gridLayout.addWidget(self.pushButton, j + 2, 11+2, 1, 1)
            self.pushButton.setText(self._translate("Dialog", "Set"))

        self.listView = QtWidgets.QListView(self.frame)
        self.listView.setGeometry(QtCore.QRect(1100, 50, 300, 600))


if __name__ == '__main__':
    print('Gen')
    # app = QtWidgets.QApplication(sys.argv)
    # Dialog = QtWidgets.QDialog()
    # ui = UI_Gens(Dialog, GenList)
    # ui.setupUI()
    # Dialog.show()
    # sys.exit(app.exec_())
