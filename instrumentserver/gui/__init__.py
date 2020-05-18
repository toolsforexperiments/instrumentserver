from .. import QtWidgets


def widgetDialog(w: QtWidgets.QWidget):
    dg = QtWidgets.QDialog()
    dg.setWindowTitle('instrumentserver')
    dg.widget = w

    lay = QtWidgets.QVBoxLayout(dg)
    lay.addWidget(w)
    lay.setContentsMargins(0, 0, 0, 0)
    dg.setLayout(lay)

    dg.show()
    return dg
