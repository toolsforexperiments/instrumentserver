from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import Qt, QRect
import sys
from pkg import hatCore as hC
from pprint import pprint

class SwitchOnOff(QtWidgets.QPushButton):

    """QPushButton for on and off.

    Type: QtWidgets.QPushButton
    """
    
    def __init__(self, parent = None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setMinimumWidth(66)
        self.setMinimumHeight(22)

    def paintEvent(self, event):
        label = "ON" if self.isChecked() else "OFF"
        bg_color = Qt.green if self.isChecked() else Qt.red

        radius = 10
        width = 32
        center = self.rect().center()

        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        painter.translate(center)
        painter.setBrush(QtGui.QColor(0,0,0))

        pen = QtGui.QPen(Qt.black)
        pen.setWidth(2)
        painter.setPen(pen)

        painter.drawRoundedRect(QRect(-width, -radius, 2*width, 2*radius), radius, radius)
        painter.setBrush(QtGui.QBrush(bg_color))
        sw_rect = QRect(-radius, -radius, width + radius, 2*radius)
        if not self.isChecked():
            sw_rect.moveLeft(-width)
        painter.drawRoundedRect(sw_rect, radius, radius)
        painter.drawText(sw_rect, Qt.AlignCenter, label)


class widgetInstrumentTabParametersTree(QtWidgets.QTabWidget):
    def __init__(self, *args):
        super().__init__(*args)
        self.args = args
    
    def setTreeHeader(self, treeWidget, headerList):
        for i in range(len(headerList)):
            treeWidget.headerItem().setText(i, headerList[i])

    def setChildText(self, childItem, textList):
        for i in range(len(textList)):
            childItem.setText(i, textList[i])

    def pos(self, x, y, width, height):
        self.width = width
        self.height = height
        self.setGeometry(QtCore.QRect(x, y, width, height))

    def processClient(self, instrDict):
        self.instrDict = {}
        self.modelDict = {}
        self.instrDict = instrDict
        # for key in cli.list_instruments():
        #     self.instrDict[key] = cli.get_instrument(key)
        # for instr in self.instrDict.keys():
        #     model = self.instrDict[instr].parameters['IDN']()['model']
        #     if model in self.modeList.keys():
        #         self.modelDict[model][instr] = self.instrDict[instr]
        #     else:
        #         self.modelDict[model] = {instr: self.instrDict[instr]}
        self.modelDict = {'vna': {'dummy_vna': instrDict['dummy_vna'], 'dummy_vna2': instrDict['dummy_vna2']},
                          'multiChan': {'dummy_multichan': instrDict['dummy_multichan']}}

    def checkSubModule(self):
        self.subLayerDict = {}
        for model in self.modelDict.keys():
            modelLayer = 0
            for instr in self.modelDict[model].keys():
                noSub = False
                subInstr = self.modelDict[model][instr].submodules
                while not noSub:
                    if not subInstr == {}:
                        modelLayer += 1
                        subInstr = subInstr[list(subInstr.keys())[0]].submodules
                    else:
                        noSub = True
            self.subLayerDict[model] = modelLayer

    def modelTab(self):
        # self.modelDict = {'VNA': {'VNA0': 1, 'VNA1': 2},
        #                   'multiChan': {'multiChan0': 3}}
        self.modelTab = {}
        self.modelTree = {}
        for model in self.modelDict.keys():
            tab = QtWidgets.QWidget()
            treeWidget = QtWidgets.QTreeWidget(tab)
            treeWidget.setGeometry(QtCore.QRect(0, 0, self.width, self.height))
            subNum = self.subLayerDict[model]
            headerList = ['Instrument'] + ['sub_{}'.format(i+1) for i in range(subNum)] + ['Parameters', 'Value', 'Unit']
            self.setTreeHeader(treeWidget, headerList)
            self.addTab(tab, model)
            self.modelTab[model] = tab
            self.modelTree[model] = treeWidget

    def instrTreeParent(self):
        self.instrTreeParentDict = {}
        for model in self.modelDict.keys():
            for instr in self.modelDict[model].keys():
                instrParentItem = QtWidgets.QTreeWidgetItem(self.modelTree[model])
                instrParentItem.setFlags(instrParentItem.flags() & ~QtCore.Qt.ItemIsSelectable)
                instrParentItem.setText(0, instr)
                self.instrTreeParentDict[instr] = instrParentItem

                for i in range(self.subLayerDict[model]):
                    for subName in self.instrDict[instr].submodules.keys():
                        instrSubParentItem = QtWidgets.QTreeWidgetItem(self.instrTreeParentDict[instr])
                        instrSubParentItem.setFlags(instrParentItem.flags() & ~QtCore.Qt.ItemIsSelectable)
                        instrSubParentItem.setText(i + 1, subName)
                        self.instrTreeParentDict[instr+subName] = instrSubParentItem

    def instrParChild(self):
        self.childList = []
        for model in self.modelDict.keys():
            subNum = self.subLayerDict[model]
            for instr in self.modelDict[model].keys():
                parameterDict = self.instrDict[instr].parameters
                for key in parameterDict.keys():
                    if key not in ['IDN', 'data', 'frequency']:
                        textList = [''] + [key, str(parameterDict[key]()), parameterDict[key].unit]
                        instrChildItem = QtWidgets.QTreeWidgetItem(self.instrTreeParentDict[instr])
                        instrChildItem.setFlags(instrChildItem.flags() | QtCore.Qt.ItemIsEditable)
                        self.setChildText(instrChildItem, textList)
                        self.childList.append([instrChildItem, int(2), parameterDict[key], type(parameterDict[key]())])

                for i in range(subNum):
                    subDict = self.instrDict[instr].submodules
                    for sub in subDict.keys():
                        parameterDict = subDict[sub].parameters
                        for key in parameterDict.keys():
                            if key not in ['IDN', 'data', 'frequency']:
                                textList = [''] + ['' for i in range(subNum)] + [key, str(parameterDict[key]()), parameterDict[key].unit]
                                instrChildItem = QtWidgets.QTreeWidgetItem(self.instrTreeParentDict[instr+sub])
                                instrChildItem.setFlags(instrChildItem.flags() | QtCore.Qt.ItemIsEditable)
                                self.setChildText(instrChildItem, textList)
                                self.childList.append([instrChildItem, int(2 + subNum), parameterDict[key], type(parameterDict[key]())])
    

    def getPar(self):
        for i in range(len(self.childList)):
            self.childList[i][0].setText(self.childList[i][1], str(self.childList[i][2]()))

    def setPar(self):
        for i in range(len(self.childList)):
            self.childList[i][2](self.childList[i][3](self.childList[i][0].text(self.childList[i][1])))

class gridLayoutWithTitle(QtWidgets.QWidget):
    def __init__(self, parent = None):
        super().__init__(parent)
        self.parent = parent

    def gridLayout(self):
        genGridLayout = QtWidgets.QGridLayout(self)
        genGridLayout.setContentsMargins(0, 0, 0, 0)
        genGridLayout.setHorizontalSpacing(10)
        genGridLayout.setVerticalSpacing(10)
        return genGridLayout

    def title(self, titleName):
        centralwidget = QtWidgets.QWidget(self.parent)
        centralwidget.setGeometry(QtCore.QRect(20, 20, leftPixel - 40, self.pixelY * 0.5 - 40))

        genTitle = QtWidgets.QLabel(genGridLayoutWidget)
        genTitle.setFont(GP.fontFunc('Arial', 20, weight=70))
        genTitle.setText(self._translate("Dialog", titleName))
        genTitle.setWordWrap(True)
        genTitle.setFixedHeight(30)
        genGridLayout.addWidget(genTitle, 0, 0, 1, 13, alignment=Qt.AlignHCenter)


def comboLabelTextWithScroll(widget, labelDict, titles=[], startX=0, startY=0):
    """Summary
    
    Parameters
    ----------
    widget : TYPE
        Description
    labelList : TYPE
        Description
    startX : int, optional
        Description
    startY : int, optional
        Description
    
    Returns
    -------
    TYPE
        Description
    
    Raises
    ------
    ValueError
        Description
    """
    _translate = QtCore.QCoreApplication.translate
    scroll = QtWidgets.QScrollArea(widget)
    scroll.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOn)
    scroll.setWidgetResizable(True)
    geom = widget.geometry().getRect()

    scroll.setFixedHeight(geom[3])
    scroll.setFixedWidth(geom[2])

    gridLayoutWidget = QtWidgets.QWidget(widget)
    gridLayout = QtWidgets.QGridLayout(gridLayoutWidget)
    gridLayout.setContentsMargins(0, 0, 0, 0)
    gridLayout.setHorizontalSpacing(10)
    gridLayout.setVerticalSpacing(10)
    scroll.setWidget(gridLayoutWidget)

    row_ = len(labelDict)
    i = 0
    if titles != []:
        for k in range(len(titles)):
            labelKey = QtWidgets.QLabel(widget)
            labelKey.setFont(hC.fontFunc('Arial', 16, weight=75))
            labelKey.setText(_translate("GUI", titles[k]))
            gridLayout.addWidget(labelKey, startX + i, startY + k, 1, 2)
        i += 1

    for key in labelDict:
        labelKey = QtWidgets.QLabel(widget)
        labelKey.setFont(hC.fontFunc('Arial', 12))
        labelKey.setText(_translate("GUI", key))
        gridLayout.addWidget(labelKey, startX + i, startY, 1, 1)

        labelValue = QtWidgets.QLabel(widget)
        labelValue.setFont(hC.fontFunc('Arial', 12))
        labelValue.setText(_translate("GUI", str(labelDict[key])))
        gridLayout.addWidget(labelValue, startX + i, startY + 1 , 1, 1)
        i += 1
    return gridLayout

def comboLabelLineEditWithScroll(widget, labelDict, titles=[], startX=0, startY=0):
    """Summary
    
    Parameters
    ----------
    widget : TYPE
        Description
    labelList : TYPE
        Description
    startX : int, optional
        Description
    startY : int, optional
        Description
    
    Returns
    -------
    TYPE
        Description
    
    Raises
    ------
    ValueError
        Description
    """
    _translate = QtCore.QCoreApplication.translate
    scroll = QtWidgets.QScrollArea(widget)
    scroll.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOn)
    scroll.setWidgetResizable(True)
    geom = widget.geometry().getRect()

    scroll.setFixedHeight(geom[3])
    scroll.setFixedWidth(geom[2])

    gridLayoutWidget = QtWidgets.QWidget(widget)
    gridLayout = QtWidgets.QGridLayout(gridLayoutWidget)
    gridLayout.setContentsMargins(0, 0, 0, 0)
    gridLayout.setHorizontalSpacing(10)
    gridLayout.setVerticalSpacing(10)
    scroll.setWidget(gridLayoutWidget)

    row_ = len(labelDict)
    i = 0
    if titles != []:
        for k in range(len(titles)):
            labelKey = QtWidgets.QLabel(widget)
            labelKey.setFont(hC.fontFunc('Arial', 16, weight=75))
            labelKey.setText(_translate("GUI", titles[k]))
            gridLayout.addWidget(labelKey, startX + i, startY + k, 1, 2)
        i += 1

    for key in labelDict:
        labelKey = QtWidgets.QLabel(widget)
        labelKey.setFont(hC.fontFunc('Arial', 12))
        labelKey.setText(_translate("GUI", key))
        gridLayout.addWidget(labelKey, startX + i, startY, 1, 1)

        lineEdit = QtWidgets.QLineEdit(widget)
        lineEdit.setClearButtonEnabled(True)
        lineEdit.setFont(hC.fontFunc('Arial', 12))
        lineEdit.setText(_translate("GUI", str(labelDict[key])))
        lineEdit.setFixedWidth(300)
        gridLayout.addWidget(lineEdit, startX + i, startY + 1 , 1, 1)
        i += 1
    return gridLayout


if __name__ == '__main__':
    print('test')