from .. import QtCore, QtWidgets, resource


def getStyleSheet():
    f = QtCore.QFile(":/style.css")
    if f.open(QtCore.QIODevice.ReadOnly | QtCore.QIODevice.Text):
        style = f.readAll()
        f.close()
        return str(style, 'utf-8')


def widgetDialog(w: QtWidgets.QWidget):
    dg = QtWidgets.QDialog()
    dg.setWindowTitle('instrumentserver')
    dg.setWindowFlag(QtCore.Qt.WindowMinimizeButtonHint)
    dg.setWindowFlag(QtCore.Qt.WindowMaximizeButtonHint)
    dg.widget = w  # type: ignore[attr-defined] # I am pretty sure the stubs are wrong for this one.

    css = getStyleSheet()
    w.setStyleSheet(css)

    lay = QtWidgets.QVBoxLayout(dg)
    lay.addWidget(w)
    lay.setContentsMargins(0, 0, 0, 0)
    dg.setLayout(lay)

    dg.show()
    return dg


def widgetMainWindow(w: QtWidgets.QWidget, name: str = 'instrumentserver'):
    mw = QtWidgets.QMainWindow()
    mw.setWindowTitle(name)
    mw.setCentralWidget(w)

    css = getStyleSheet()
    w.setStyleSheet(css)

    mw.show()
    return mw


def keepSmallHorizontally(w: QtWidgets.QWidget):
    w.setSizePolicy(
        QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Fixed,
                              QtWidgets.QSizePolicy.Minimum)
    )

