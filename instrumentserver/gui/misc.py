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


class AlertLabelGreen(AlertLabel):
    """
    Expanding the functionality of the AlertLabel to add green alerts to indicate successful things
    """
    def mouseDoubleClickEvent(self, a0: QtGui.QMouseEvent) -> None:
        self.clearAlert()
        super().mouseDoubleClickEvent(a0)

    def mousePressEvent(self, ev: QtGui.QMouseEvent) -> None:
        if ev.buttons() == QtCore.Qt.MidButton:
            self.clearAlert()
        super().mousePressEvent(ev)

    @QtCore.Slot(str)
    def setSuccssefulAlert(self, message: str):
        pix = QtGui.QIcon(":/icons/green-alert.svg").pixmap(*self._pixmapSize)
        self.setPixmap(pix)
        self.setToolTip(message)


class DetachedTab(QtWidgets.QDialog):

    #: Signal(QtWidgets.QWidget)
    #: emitted when a tab for the instrument is closed
    onCloseSignal = QtCore.Signal(object, str)

    def __init__(self, contentWidget: QtWidgets.QWidget, name: str, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.name = name
        self.widget = contentWidget

        self.setWindowTitle(name)
        self.setGeometry(self.widget.frameGeometry())

        layout = QtWidgets.QVBoxLayout(self)
        self.setLayout(layout)

        layout.addWidget(self.widget)

        self.widget.show()

    def closeEvent(self, a0: QtGui.QCloseEvent) -> None:
        self.onCloseSignal.emit(self.widget, self.name)


class SeparableTabBar(QtWidgets.QTabBar):
    separateTab = QtCore.Signal(object, object)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.selectedIndex = 0
        self.pressing = False
        self.initialPosition = QtCore.QPoint()
        self.finalPosition = QtCore.QPoint()

    def mousePressEvent(self, a0: QtGui.QMouseEvent) -> None:
        self.pressing = True
        self.initialPosition = a0.pos()
        self.selectedIndex = self.tabAt(self.initialPosition)
        super().mousePressEvent(a0)

    def mouseMoveEvent(self, a0: QtGui.QMouseEvent) -> None:

        # Here would go a preview of the widget underneath
        super().mouseMoveEvent(a0)

    def mouseReleaseEvent(self, a0: QtGui.QMouseEvent) -> None:
        self.pressing = False
        self.finalPosition = a0.pos()
        # FIXME: Replace the hardcoded number for either a variable or the drag position of the application
        if (self.finalPosition - self.initialPosition).manhattanLength() > 25 and self.selectedIndex != -1:
            self.separateTab.emit(self.selectedIndex, a0.globalPos())

        a0.accept()
        super().mouseReleaseEvent(a0)


class SeparableTabWidget(QtWidgets.QTabWidget):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._tabBar = SeparableTabBar(self)
        self.setTabBar(self._tabBar)
        self._tabBar.separateTab.connect(self.separateTab)

    @QtCore.Slot(object, object)
    def separateTab(self, tab, point: QtCore.QPoint):
        widget = self.widget(tab)
        name = self.tabText(tab)
        detachedTab = DetachedTab(widget, name, parent=self)
        widgetGeometry = widget.frameGeometry()
        movedPoint = QtCore.QPoint(point.x() - widgetGeometry.width()//2, point.y() - widgetGeometry.height()//2)
        detachedTab.move(movedPoint)
        detachedTab.onCloseSignal.connect(self.attatchTab)
        detachedTab.show()

    @QtCore.Slot(object, str)
    def attatchTab(self, widget, name):
        self.addTab(widget, name)

