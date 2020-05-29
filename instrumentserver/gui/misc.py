from typing import Optional, Tuple

from .. import QtWidgets, QtGui, resource, QtCore


class AlertLabel(QtWidgets.QLabel):

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None,
                 pixmapSize: Optional[Tuple[int, int]] = (20, 20)):
        super().__init__(parent)

        self.setAlignment(QtCore.Qt.AlignVCenter | QtCore.Qt.AlignHCenter)
        self._pixmapSize = pixmapSize
        pix = QtGui.QIcon(":/icons/no-alert.svg").pixmap(*pixmapSize)
        self.setPixmap(pix)
        self.setToolTip('no alerts')

    @QtCore.Slot(str)
    def setAlert(self, message: str):
        pix = QtGui.QIcon(":/icons/red-alert.svg").pixmap(*self._pixmapSize)
        self.setPixmap(pix)
        self.setToolTip(message)

    @QtCore.Slot()
    def clearAlert(self):
        pix = QtGui.QIcon(":/icons/no-alert.svg").pixmap(*self._pixmapSize)
        self.setPixmap(pix)
        self.setToolTip('no alerts')
