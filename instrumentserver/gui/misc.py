from typing import Optional, Tuple

from .. import QtWidgets, QtGui, QtCore


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


class DetachedTab(QtWidgets.QMainWindow):

    #: Signal(QtWidgets.QWidget)
    #: emitted when a tab for the instrument is closed
    onCloseSignal = QtCore.Signal(object, str)

    def __init__(self, contentWidget: QtWidgets.QWidget, name: str, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.name = name
        self.widget = contentWidget

        self.setWindowTitle(name)
        self.setGeometry(self.widget.frameGeometry())
        self.setCentralWidget(self.widget)

        self.widget.show()

    def closeEvent(self, a0: QtGui.QCloseEvent) -> None:
        self.onCloseSignal.emit(self.widget, self.name)


class SeparableTabBar(QtWidgets.QTabBar):

    #: Signal(tabIndex, newPosition)
    #: Emitted when the user is dragging a tab out ofd the tab bar and should be detached.
    onDetachTab = QtCore.Signal(object, object)

    #: Signal(oldIndex, newIndex)
    #: Emitted when the user is moving the tabs.
    onMoveTab = QtCore.Signal(int, int)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.selectedIndex = 0
        self.dragStartPos = QtCore.QPoint()
        self.dragDroppedPos = QtCore.QPoint()
        self.setElideMode(QtCore.Qt.ElideRight)
        self.setAcceptDrops(True)

    def mousePressEvent(self, a0: QtGui.QMouseEvent) -> None:
        if a0.button() == QtCore.Qt.LeftButton:
            self.dragStartPos = a0.pos()

        self.dragDroppedPos.setX(0)
        self.dragDroppedPos.setY(0)

        self.selectedIndex = self.tabAt(self.dragStartPos)
        super().mousePressEvent(a0)

    def mouseDoubleClickEvent(self, a0: QtGui.QMouseEvent) -> None:
        self.onDetachTab.emit(self.tabAt(a0.pos()), a0.globalPos())
        a0.accept()

    def mouseMoveEvent(self, a0: QtGui.QMouseEvent) -> None:
        """
        Detects if the user is dragging a tab and starts the drag object.
        """

        if (a0.pos() - self.dragStartPos).manhattanLength() > QtWidgets.QApplication.startDragDistance() \
                and self.selectedIndex != -1:

            drag = QtGui.QDrag(self)
            mimeData = QtCore.QMimeData()
            mimeData.setData('action', b'application/tab-detach')
            drag.setMimeData(mimeData)

            pixmap = self.parentWidget().currentWidget().grab()
            targetPixmap = QtGui.QPixmap(pixmap.size())
            targetPixmap.fill(QtCore.Qt.transparent)
            painter = QtGui.QPainter(targetPixmap)
            painter.drawPixmap(0, 0, pixmap)
            painter.end()
            drag.setPixmap(targetPixmap)

            dropAction = drag.exec_(QtCore.Qt.MoveAction | QtCore.Qt.CopyAction)

            # In linux the drag.exec_ does not return MoveAction, so it must be set manually.
            if self.dragDroppedPos.x() != 0 and self.dragDroppedPos.y() != 0:
                dropAction = QtCore.Qt.MoveAction

            # A move action indicates that the user is trying to move the tabs around
            if dropAction == QtCore.Qt.MoveAction:
                a0.accept()
                self.onMoveTab.emit(self.tabAt(self.dragStartPos), self.tabAt(self.dragDroppedPos))

            # An ignore action means that the user dropped the tab outside of the window and should be detached.
            elif dropAction == QtCore.Qt.IgnoreAction:
                a0.accept()
                self.onDetachTab.emit(self.selectedIndex, self.cursor().pos())

        else:
            super().mouseMoveEvent(a0)

    def dragEnterEvent(self, a0: QtGui.QDragEnterEvent) -> None:
        mimeData = a0.mimeData()
        formats = mimeData.formats()

        if 'action' in formats and mimeData.data('action') == 'application/tab-detach':
            a0.acceptProposedAction()

        super().dragMoveEvent(a0)

    def dropEvent(self, a0: QtGui.QDropEvent) -> None:
        self.dragDroppedPos = a0.pos()
        super().dropEvent(a0)

    def mouseReleaseEvent(self, a0: QtGui.QMouseEvent) -> None:
        a0.accept()
        super().mouseReleaseEvent(a0)


class DetachableTabWidget(QtWidgets.QTabWidget):
    """
    TabWidget whose tabs can be detached and moved around.
    You can add 2 different kind of tabs, unclosable tabs and regular tabs. To add unclosable tabs used the
    addUnclosableTab method, while to add closable tabs use addTab method.
    """

    #: Signal(str)
    #: Emitted when a tab got closed.
    onTabClosed = QtCore.Signal(str)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._tabBar = SeparableTabBar(self)
        self._tabBar.setTabsClosable(True)
        self._tabBar.tabCloseRequested.connect(self.onCloseTab)
        self.setTabBar(self._tabBar)
        self._tabBar.onDetachTab.connect(self.onDetachTab)
        self._tabBar.onMoveTab.connect(self.onMoveTab)

        self.unclosableTabs = {}

    def addUnclosableTab(self, widget, name):
        index = self.addTab(widget, name)
        closeButton = self._tabBar.tabButton(index, QtWidgets.QTabBar.ButtonPosition.RightSide)
        # on Mac the button is on the left side
        if closeButton is None:
            closeButton = self._tabBar.tabButton(index, QtWidgets.QTabBar.ButtonPosition.LeftSide)
        closeButton.resize(0, 0)
        self.unclosableTabs[name] = widget

    @QtCore.Slot(object, object)
    def onDetachTab(self, tab, point: QtCore.QPoint):
        """
        Gets triggered when the user drags out a tab. Opens a QMainWindow with the widget in the dragged tab.
        """
        widget = self.widget(tab)
        name = self.tabText(tab)
        self.removeTab(self.indexOf(widget))
        detachedTab = DetachedTab(widget, name, parent=self)
        movedPoint = QtCore.QPoint(point.x(), point.y())
        detachedTab.move(movedPoint)
        detachedTab.onCloseSignal.connect(self.onAttatchTab)
        detachedTab.show()

    @QtCore.Slot(object, str)
    def onAttatchTab(self, widget, name):
        """
        Gets called when the user closes one of the detachable windows and properly attaches the tab back.
        """
        if name in self.unclosableTabs:
            self.addUnclosableTab(widget, name)
        else:
            index = self.addTab(widget, name)

    @QtCore.Slot(int, int)
    def onMoveTab(self, fromIndex, toIndex):
        widget = self.widget(fromIndex)
        icon = self.tabIcon(fromIndex)
        text = self.tabText(fromIndex)

        self.onCloseTab(fromIndex, True)
        self.insertTab(toIndex, widget, icon, text)
        if text in self.unclosableTabs:
            self._tabBar.tabButton(toIndex, QtWidgets.QTabBar.ButtonPosition.RightSide).resize(0, 0)
        self.setCurrentWidget(widget)

    @QtCore.Slot(int)
    def onCloseTab(self, index, moving=False):
        """
        Closes the tab at index.

        :param index: Closes the tab at this index
        :param moving: If True, will not emit any signals.
        """
        name = self.tabText(index)
        widget = self.widget(index)
        widget.close()
        widget = None
        self.removeTab(index)

        # When moving the tabs, we don't want to emit the signal since the tab is not being closed, just moved.
        if not moving:
            self.onTabClosed.emit(name)


class BaseDialog(QtWidgets.QDialog):
    """
    Base dialog for internal purposes. Has correct flags so that the question mark does not appear.
    Also overload set tittle such that the size of the window gets adjusted in a way that the tittle is not clipped.

    :param tittleBarButtonsWidth: The width of pixels that the icon, the width will be set such that it is this number
        plus whatever the tittle is plus 15 extra pixels of margin.
    """
    def __init__(self, parent=None, flags=(QtCore.Qt.CustomizeWindowHint | QtCore.Qt.WindowCloseButtonHint), tittleBarButtonsWidth=108):
        super().__init__(parent, flags=flags)
        self.tittleBarButtonsWidth = tittleBarButtonsWidth

    def setWindowTitle(self, p_str):
        super().setWindowTitle(p_str)
        tittleWidth = self.fontMetrics().boundingRect(p_str).size().width()
        minWidth = self.tittleBarButtonsWidth + tittleWidth + 15
        if self.width() < minWidth:
            self.resize(minWidth, self.height())
