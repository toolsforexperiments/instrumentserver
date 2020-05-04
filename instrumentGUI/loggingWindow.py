# -*- coding: utf-8 -*-
"""
Created on Thu Apr 30 08:45:11 2020

@author: Pinlei
"""

import sys
from qtpy import QtGui, QtCore, QtWidgets
import GUIpackage as GP


newInstrList = GP.jsonToDict_TypeOrder("instrJson.json")
instrTypeList = list(newInstrList.keys())


def fontFunc(fontName, size, **kwargs):
    weight_ = kwargs.get("weight", 50)
    font = QtGui.QFont()
    font.setFamily(fontName)
    font.setPointSize(size)
    font.setWeight(weight_)
    return font


class UI_Dialog(object):


    def setupUI(self, win_):
        _translate = QtCore.QCoreApplication.translate
        win_.setObjectName("Logging")
        win_.resize(1920, 1080)
        win_.setWindowTitle(_translate("MainWindow", "Hat Logging"))

        self.formLayoutWidget = QtWidgets.QWidget(win_)  # All instruments form
        self.formLayoutWidget.setGeometry(QtCore.QRect(120, 90, 800, 900))
        self.formLayout = QtWidgets.QFormLayout(self.formLayoutWidget)
        self.formLayout.setContentsMargins(0, 0, 0, 0)
        self.formLayout.setVerticalSpacing(20)
        self.formLayout.setHorizontalSpacing(20)

        for i in range(len(instrTypeList)):
            self.label = QtWidgets.QLabel(self.formLayoutWidget)
            self.label.setFont(fontFunc('Arial', 12, weight=75))
            self.label.setText(_translate("MainWindow", instrTypeList[i]))
            self.formLayout.setWidget(i+1, QtWidgets.QFormLayout.LabelRole, self.label)


            self.gridLayout = QtWidgets.QGridLayout()  # All intsruments in each type
            self.gridLayout.setVerticalSpacing(5)
            self.formLayout.setLayout(i+1, QtWidgets.QFormLayout.FieldRole, self.gridLayout)
            allInstrInType = newInstrList[instrTypeList[i]]

            for j in range(len(allInstrInType)):
                self.radioButton = QtWidgets.QRadioButton(self.formLayoutWidget)
                self.radioButton.setChecked(True)
                self.radioButton.setAutoExclusive(False)
                self.radioButton.setFont(fontFunc('Arial', 10))
                self.radioButton.setText(_translate("MainWindow", allInstrInType[j]['instrName']))
                self.gridLayout.addWidget(self.radioButton, j, 0, 1, 1)

                self.label = QtWidgets.QLabel(self.formLayoutWidget)
                self.label.setFont(fontFunc('Arial', 10))
                self.label.setText(_translate("MainWindow",  allInstrInType[j]['memo']))
                self.gridLayout.addWidget(self.label, j, 1, 1, 1)

                self.lineEdit = QtWidgets.QLineEdit(self.formLayoutWidget)
                self.lineEdit.setClearButtonEnabled(True)
                self.lineEdit.setFont(fontFunc('Arial', 10))
                self.lineEdit.setFixedWidth(300)
                self.lineEdit.setText(_translate("MainWindow",  allInstrInType[j]['default_name']))
                self.gridLayout.addWidget(self.lineEdit, j, 2, 1, 1)

if __name__ == '__main__':
    app = QtWidgets.QApplication(sys.argv)
    Dialog = QtWidgets.QMainWindow()
    ui = UI_Dialog()
    ui.setupUI(Dialog)
    Dialog.show()
    sys.exit(app.exec_())
