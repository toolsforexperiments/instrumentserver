from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import Qt, QRect
import sys


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



