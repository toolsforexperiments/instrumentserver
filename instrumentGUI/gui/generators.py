from qtpy import QtGui, QtCore, QtWidgets
from qtpy.QtCore import Qt, QRect
from typing import Optional, List, Any, Dict, List, Tuple, Union
import numpy as np


class customQLineEdit(QtWidgets.QLineEdit):
    def __init__(self, parent: Optional[QtWidgets.QWidget] = None, keyMapList: List = [Qt.Key_W, Qt.Key_A, Qt.Key_S, Qt.Key_D, Qt.Key_Q, Qt.Key_E]):
        super().__init__(parent)
        self.keyMapList = keyMapList

    def advancedKeyPressEvent(self, event):
        if event.key() == self.keyMapList[1]:
            self.leftCursor()
        elif event.key() == self.keyMapList[3]:
            self.rightCursor()
        else:
            event.ignore()

    def leftCursor(self):
        cursorX = self.cursorPosition()
        selS = self.selectionStart()
        if selS == 0:
            pass
        else:
            if selS == -1:
                self.setSelection(cursorX - 1, -1)
            else:
                self.setSelection(selS - 1, 1)

    def rightCursor(self):
        cursorX = self.cursorPosition()
        selS = self.selectionStart()
        if self.selectedText() == " ":
            pass
        else:
            if selS == -1:
                self.setSelection(cursorX, 1)
            else:
                self.setSelection(selS + 1, 1)


class controlDoubleSpinBox(QtWidgets.QDoubleSpinBox):
    def __init__(self, parent: Optional[QtWidgets.QWidget] = None, keyMapList: List = [Qt.Key_W, Qt.Key_A, Qt.Key_S, Qt.Key_D, Qt.Key_Q, Qt.Key_E]):
        super().__init__(parent)
        self.keyMapList = keyMapList
        self.setLineEdit(customQLineEdit(keyMapList=keyMapList))

    def keyPressEvent(self, event):
        super().keyPressEvent(event)
        event.ignore()

    def advancedKeyPressEvent(self, event):
        self.lineEdit().advancedKeyPressEvent(event)
        if event.key() == self.keyMapList[0]:
            self.upCursor()
        elif event.key() == self.keyMapList[2]:
            self.downCursor()
        else:
            event.ignore()


    def findDigit(self):
        try:
            digit = int(np.floor(np.log10(np.abs(self.value()))))
        except OverflowError:
            digit = 0

        if digit <= 0:
            digit = 0
        return digit

    def setSelStep(self):
        digit = self.findDigit()
        step = int(self.lineEdit().selectionStart())

        if self.value() < 0:
            digit += 1

        if step <= digit:
            self.setSingleStep(10**(-step + digit))
        elif step == digit + 1:
            self.setSingleStep(0)
        else:
            self.setSingleStep(10**(-step + 1 + digit))
        return step

    def upCursor(self):
        oldValue = self.value()
        oldDigit = self.findDigit()
        step = self.setSelStep()
        self.stepBy(1)
        newDigit = self.findDigit()
        if newDigit != oldDigit:
            if self.value() > 0:
                step += 1
            else:
                step -= 1
        if oldValue < 0 and self.value() >= 0:
            step -= 1
        self.lineEdit().setSelection(step, 1)

    def downCursor(self):
        oldDigit = self.findDigit()
        oldValue = self.value()
        step = self.setSelStep()
        self.stepBy(-1)
        newDigit = self.findDigit()
        if newDigit != oldDigit:
            if self.value() > 0:
                step -= 1
            else:
                step += 1
        if oldValue >= 0 and self.value() < 0:
            step += 1
        self.lineEdit().setSelection(step, 1)


class GeneraotrControlWidget(QtWidgets.QWidget):
    def __init__(self, parent: Optional[QtWidgets.QWidget] = None):
        super().__init__(parent)

        self.lineFont = QtGui.QFont()
        self.lineFont.setPointSize(20)

        layout = QtWidgets.QGridLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.freqEdit = controlDoubleSpinBox(self)
        self.freqEdit.setFixedWidth(400)
        self.freqEdit.setRange(0, 20)
        self.freqEdit.setDecimals(9)
        self.freqEdit.setFont(self.lineFont)
        self.freqEdit.setValue(5.323568234)
        self.freqEdit.setSuffix(" GHz")
        self.freqEdit.setSingleStep(0.1)
        self.freqEdit.setButtonSymbols(1)
        lbl = QtWidgets.QLabel("Freq: ")
        lbl.setAlignment(Qt.AlignRight)
        lbl.setFont(self.lineFont)
        layout.addWidget(lbl, 0, 0)
        layout.addWidget(self.freqEdit, 0, 1)

        self.setLayout(layout)

        self.powerEdit = controlDoubleSpinBox(self,keyMapList=[Qt.Key_I, Qt.Key_J, Qt.Key_K, Qt.Key_L, Qt.Key_U, Qt.Key_O])
        self.powerEdit.setFixedWidth(400)
        self.powerEdit.setRange(-180, 20)
        self.powerEdit.setDecimals(2)
        self.powerEdit.setFont(self.lineFont)
        self.powerEdit.setValue(3.00)
        self.powerEdit.setSuffix(" dBm")
        self.powerEdit.setButtonSymbols(1)

        lbl = QtWidgets.QLabel("Power: ")
        lbl.setAlignment(Qt.AlignRight)
        lbl.setFont(self.lineFont)
        layout.addWidget(lbl, 1, 0)
        layout.addWidget(self.powerEdit, 1, 1)
        self.setLayout(layout)

        def printCursor():
            print('Helo')

        def keyPressEvent(self, event):
            print(event.key())

        testButton = QtWidgets.QPushButton(self)
        testButton.setText('test')
        testButton.clicked.connect(printCursor)
        layout.addWidget(testButton, 2, 0)

    def keyPressEvent(self, event):
        self.powerEdit.advancedKeyPressEvent(event)
        self.freqEdit.advancedKeyPressEvent(event)