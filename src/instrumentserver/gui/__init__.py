from typing import Optional

from .. import (
    QtCore,
    QtWidgets,
    resource,  # noqa: F401
)


def getStyleSheet() -> Optional[str]:
    f = QtCore.QFile(":/style.css")
    if f.open(
        QtCore.QIODevice.OpenModeFlag.ReadOnly | QtCore.QIODevice.OpenModeFlag.Text
    ):  # type: ignore[call-overload]
        style = f.readAll()
        f.close()
        return str(style, "utf-8")
    return None


def widgetDialog(w: QtWidgets.QWidget) -> QtWidgets.QDialog:
    dg = QtWidgets.QDialog()
    dg.setWindowTitle("instrumentserver")
    dg.setWindowFlag(QtCore.Qt.WindowType.WindowMinimizeButtonHint)
    dg.setWindowFlag(QtCore.Qt.WindowType.WindowMaximizeButtonHint)
    dg.widget = w

    css = getStyleSheet()
    w.setStyleSheet(css)

    lay = QtWidgets.QVBoxLayout(dg)
    lay.addWidget(w)
    lay.setContentsMargins(0, 0, 0, 0)
    dg.setLayout(lay)

    dg.show()
    return dg


def widgetMainWindow(
    w: QtWidgets.QWidget, name: str = "instrumentserver"
) -> QtWidgets.QMainWindow:
    mw = QtWidgets.QMainWindow()
    mw.setWindowTitle(name)
    mw.setCentralWidget(w)

    css = getStyleSheet()
    w.setStyleSheet(css)

    mw.show()
    return mw


def keepSmallHorizontally(w: QtWidgets.QWidget) -> None:
    w.setSizePolicy(
        QtWidgets.QSizePolicy(
            QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Minimum
        )
    )
