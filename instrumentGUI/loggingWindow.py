# -*- coding: utf-8 -*-
"""
Created on Thu Apr 30 08:45:11 2020

@author: Pinlei
"""

import sys
import os
import json
from qtpy import QtGui, QtCore, QtWidgets
from pkg import hatWidgets as hW
import GUIpackage as GP
import generators as GUIgen
import numpy as np

GP.createAllProjectsDir()
numInst, newInstrList = GP.jsonToDict_TypeOrder("instrJson.json")
instrTypeList = list(newInstrList.keys())

class UI_MainWindow(object):
    def __init__(self, win_):
        self.pixelY = 1080
        self.ratio = 16/9
        self.pixelX = self.pixelY * self.ratio
        self._translate = QtCore.QCoreApplication.translate
        self.win_ = win_
        self.win_.setObjectName("Logging")
        self.win_.resize(self.pixelX, self.pixelY)
        self.win_.setWindowTitle(self._translate("MainWindow", "Hat Logging"))

    def setupUI(self):
        self.loggingGUI()
        self.instrListGUI()
        self.selectingGUI()
        self.pushButton = QtWidgets.QPushButton(self.win_)
        self.pushButton.setGeometry(QtCore.QRect((self.pixelX-600)/2, self.pixelY-100, 600, 50))
        self.pushButton.setFont(GP.fontFunc('Arial', 15, weight=50))
        self.pushButton.setText(self._translate("MainWindow", "Logging, start doing experiment :)"))
        self.pushButton.clicked.connect(self.open_dialog)

    def loggingGUI(self):
        instX = int(self.pixelX * 0.4)
        instY = int(self.pixelY * 0.35)

        gridLayoutWidget = QtWidgets.QWidget(self.win_)
        gridLayoutWidget.setGeometry(QtCore.QRect(10, 100, instX, instY))

        labelList = np.array([['Name', '', 'Project', ''], ['ProjectVersion', 'V1', '', '']])
        gridLayout, self.infoEditMatrix = GP.combo_label_lineEdit(gridLayoutWidget, labelList)

        label = QtWidgets.QLabel(gridLayoutWidget)
        label.setFont(GP.fontFunc('Arial', 12))
        label.setText(self._translate("MainWindow", 'FridgeName'))
        gridLayout.addWidget(label, 1, 2, 1, 1)

        comboBoxFridge = QtWidgets.QComboBox(gridLayoutWidget)
        comboBoxFridge.setFont(GP.fontFunc('Arial', 12))
        comboBoxFridge.addItem("CoolRunnings")
        comboBoxFridge.addItem("Texas")
        gridLayout.addWidget(comboBoxFridge, 1, 3, 1, 1)

        label = QtWidgets.QLabel(gridLayoutWidget)
        label.setFont(GP.fontFunc('Arial', 12))
        label.setText(self._translate("MainWindow", 'Date'))
        gridLayout.addWidget(label, 2, 0, 1, 1)

        dateEdit = QtWidgets.QDateEdit(gridLayoutWidget)
        dateEdit.setDateTime(QtCore.QDateTime.currentDateTime())
        dateEdit.setFont(GP.fontFunc('Arial', 12))
        dateEdit.setFixedHeight(50)
        gridLayout.addWidget(dateEdit, 2, 1, 1, 1)

        label = QtWidgets.QLabel(gridLayoutWidget)
        label.setFont(GP.fontFunc('Arial', 12))
        label.setText(self._translate("MainWindow", 'Directory'))
        gridLayout.addWidget(label, 2, 2, 1, 1)

        comboBoxDir = QtWidgets.QComboBox(gridLayoutWidget)
        comboBoxDir.setFont(GP.fontFunc('Arial', 12))
        comboBoxDir.addItem("N:\\Data\\")
        comboBoxDir.addItem("H:\\Data\\")
        comboBoxDir.addItem("D:\\Data\\")
        gridLayout.addWidget(comboBoxDir, 2, 3, 1, 1)

        self.infoList = [dateEdit, comboBoxFridge, comboBoxDir]

        saveButton = QtWidgets.QPushButton(self.win_)
        saveButton.setFont(GP.fontFunc('Arial', 15, weight=50))
        saveButton.setText(self._translate("MainWindow", "Save"))
        saveButton.clicked.connect(self.saveInfo)
        gridLayout.addWidget(saveButton, 3, 0, 1, 2)

        resetButton = QtWidgets.QPushButton(self.win_)
        resetButton.setFont(GP.fontFunc('Arial', 15, weight=50))
        resetButton.setText(self._translate("MainWindow", "Reset"))
        resetButton.clicked.connect(self.resetInfo)
        gridLayout.addWidget(resetButton, 3, 2, 1, 2)

    def selectingGUI(self):
        instX = int(self.pixelX * 0.4)
        instY = int(self.pixelY * 0.35)
        centralwidget = QtWidgets.QWidget(MainWindow)
        centralwidget.setGeometry(QtCore.QRect(10, 100 + instY, instX, instY))

        scroll = QtWidgets.QScrollArea(centralwidget)
        scroll.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOn)
        scroll.setWidgetResizable(True)
        scroll.setFixedHeight(instY)
        scroll.setFixedWidth(instX)

        self.treeWidget = QtWidgets.QTreeWidget(centralwidget)
        self.treeWidget.headerItem().setText(0, self._translate("MainWindow", "Name"))
        self.treeWidget.headerItem().setText(1, self._translate("MainWindow", "Project"))
        self.treeWidget.headerItem().setText(2, self._translate("MainWindow", "Version"))
        self.treeWidget.headerItem().setText(3, self._translate("MainWindow", "Others"))
        
        try:
            with open('./static/allProjects.json', 'r') as jsonOpen_:
                jsonOpen = json.load(jsonOpen_)
                fatherList= list(jsonOpen.keys())
                self.fatherItems = {}
                for fatherName in fatherList:
                    fatherItem = QtWidgets.QTreeWidgetItem(self.treeWidget)
                    fatherItem.setFlags(fatherItem.flags() & ~QtCore.Qt.ItemIsSelectable)
                    fatherItem.setText(0, self._translate('MainWindow', fatherName))
                    for sonDic in jsonOpen[fatherName]:
                        sonItem = QtWidgets.QTreeWidgetItem(fatherItem)
                        sonItem.setText(0, self._translate('MainWindow', sonDic['name']))
                        sonItem.setText(1, self._translate('MainWindow', sonDic['project']))
                        sonItem.setText(2, self._translate('MainWindow', sonDic['version']))
                        sonItem.setText(3, self._translate('MainWindow', sonDic['directory']+sonDic['fridgeName']+"\\"+sonDic['date']))
                    self.fatherItems[fatherName] = fatherItem
        except FileNotFoundError:
            pass


        scroll.setWidget(self.treeWidget)

    def instrListGUI(self):
        instX = 1000
        instY = numInst * 50

        centralwidget = QtWidgets.QWidget(self.win_)
        centralwidget.setGeometry(QtCore.QRect((self.pixelX-instX)-100, 100, instX, instY))

        formLayoutWidget = QtWidgets.QWidget(self.win_)  # All instruments form
        formLayout = QtWidgets.QFormLayout(formLayoutWidget)
        formLayout.setContentsMargins(0, 0, 0, 0)
        formLayout.setVerticalSpacing(10)
        formLayout.setHorizontalSpacing(30)

        scroll = QtWidgets.QScrollArea(centralwidget)
        scroll.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOn)
        scroll.setWidgetResizable(True)
        scroll.setFixedHeight(int(self.pixelY * 0.7))
        scroll.setFixedWidth(instX)
        scroll.setWidget(formLayoutWidget)

        self.checkBoxList = {}
        self.lineEditList = {}

        for i in range(len(instrTypeList)):
            label = QtWidgets.QLabel(formLayoutWidget)
            label.setFont(GP.fontFunc('Arial', 12, weight=75))
            label.setText(self._translate("MainWindow", instrTypeList[i]))
            formLayout.setWidget(i+1, QtWidgets.QFormLayout.LabelRole, label)


            gridLayout = QtWidgets.QGridLayout()  # All intsruments in each type
            gridLayout.setVerticalSpacing(5)
            formLayout.setLayout(i+1, QtWidgets.QFormLayout.FieldRole, gridLayout)
            allInstrInType = newInstrList[instrTypeList[i]]

            self.checkBoxList[instrTypeList[i]] = []
            self.lineEditList[instrTypeList[i]] = []

            for j in range(len(allInstrInType)):
                checkBox = QtWidgets.QCheckBox(formLayoutWidget)
                checkBox.setChecked(True)
                checkBox.setFont(GP.fontFunc('Arial', 10))
                checkBox.setText(self._translate("MainWindow", allInstrInType[j]['instrName']))
                gridLayout.addWidget(checkBox, j, 0, 1, 1)

                label = QtWidgets.QLabel(formLayoutWidget)
                label.setFont(GP.fontFunc('Arial', 10))
                label.setText(self._translate("MainWindow", allInstrInType[j]['memo']))
                gridLayout.addWidget(label, j, 1, 1, 1)

                lineEdit = QtWidgets.QLineEdit(formLayoutWidget)
                lineEdit.setClearButtonEnabled(True)
                lineEdit.setFont(GP.fontFunc('Arial', 10))
                lineEdit.setFixedWidth(300)
                lineEdit.setText(self._translate("MainWindow", allInstrInType[j]['default_name']))
                gridLayout.addWidget(lineEdit, j, 2, 1, 1)

                self.checkBoxList[instrTypeList[i]].append(checkBox)
                self.lineEditList[instrTypeList[i]].append(lineEdit)


    def open_dialog(self):
        GenList = []
        for i in range(len(self.checkBoxList['Generator'])):
            if self.checkBoxList['Generator'][i].isChecked():
                GenList.append(self.lineEditList['Generator'][i].text())
        dialog = QtWidgets.QDialog()
        dialog.ui = GUIgen.UI_Gens(dialog, GenList)
        dialog.ui.setupUI()
        dialog.exec_()


    def resetInfo(self):
        for lineEdit in self.infoEditMatrix.flatten():
            lineEdit.setText("")


    def saveInfo(self):
        directory_ = self.infoList[2].currentText()
        name_ = self.infoEditMatrix.flatten()[0].text()
        project_ = self.infoEditMatrix.flatten()[1].text()
        version_ = self.infoEditMatrix.flatten()[2].text()
        fridgeName_ = self.infoList[1].currentText()
        date_ = self.infoList[0].date().toString("yyyy_MM_dd")
        dir_ = directory_ + name_ + "\\" + project_ + "_" + version_ + "\\" + fridgeName_ + "_" + date_ + "\\"
        savingDic = {"name": name_,
                     "project": project_,
                     "version": version_,
                     "fridgeName": fridgeName_,
                     "date": date_,
                     "directory": directory_}
        json_ = json.dumps(savingDic)
        try:
            with open('./static/allProjects.json', 'r+') as jsonSave:
                jsonOpen = json.load(jsonSave)
                if savingDic["name"] in list(jsonOpen.keys()):
                    if savingDic in jsonOpen[savingDic["name"]]:
                        print('project already exist, continue.')
                    else:
                        jsonOpen[savingDic["name"]].append(savingDic)
                        sonItem = QtWidgets.QTreeWidgetItem(self.fatherItems[savingDic["name"]])
                        sonItem.setText(0, self._translate('MainWindow', savingDic['name']))
                        sonItem.setText(1, self._translate('MainWindow', savingDic['project']))
                        sonItem.setText(2, self._translate('MainWindow', savingDic['version']))
                        sonItem.setText(3, self._translate('MainWindow', savingDic['directory']+savingDic['fridgeName']+"\\"+savingDic['date']))
                else:
                    jsonOpen[savingDic["name"]] = [savingDic]
                    fatherItem = QtWidgets.QTreeWidgetItem(self.treeWidget)
                    fatherItem.setFlags(fatherItem.flags() & ~QtCore.Qt.ItemIsSelectable)
                    fatherItem.setText(0, self._translate('MainWindow', savingDic["name"]))
                    self.fatherItems[savingDic["name"]] = fatherItem
                    sonItem = QtWidgets.QTreeWidgetItem(self.fatherItems[savingDic["name"]])
                    sonItem.setText(0, self._translate('MainWindow', savingDic['name']))
                    sonItem.setText(1, self._translate('MainWindow', savingDic['project']))
                    sonItem.setText(2, self._translate('MainWindow', savingDic['version']))
                    sonItem.setText(3, self._translate('MainWindow', savingDic['directory']+savingDic['fridgeName']+"\\"+savingDic['date']))


            with open('./static/allProjects.json', 'w') as jsonSave:
                json.dump(jsonOpen, jsonSave)

        except FileNotFoundError:
            with open('./static/allProjects.json', 'w') as jsonSave:
                json.dump({savingDic["name"]: [savingDic]}, jsonSave)
        
        try:
            os.makedirs(dir_)
        except FileExistsError:
            print("Directory exist, make sure didn't overwrite other people's data")
            pass

        return

if __name__ == '__main__':
    app = QtWidgets.QApplication(sys.argv)
    MainWindow = QtWidgets.QMainWindow()
    ui = UI_MainWindow(MainWindow)
    ui.setupUI()
    MainWindow.show()
    sys.exit(app.exec_())
