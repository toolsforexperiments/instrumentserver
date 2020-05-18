from typing import Any, Optional, List
import logging

from qcodes import Parameter

from .. import QtWidgets, QtCore, QtGui, resource

from . import keepSmallHorizontally


logger = logging.getLogger(__name__)


class ParameterWidget(QtWidgets.QWidget):
    """A widget that allows editing and/or displaying a parameter value."""

    # TODO: a method to show that there's a return value of some sort

    #: Signal(Any) --
    #: emitted when the parameter was set successfully
    parameterSet = QtCore.Signal(object)

    #: Signal(str) ---
    #: emitted when setting gave an error. Argument is the error message.
    parameterSetError = QtCore.Signal(str)

    #: Signal(Any) --
    #: emitted when the parameter value is pending
    parameterPending = QtCore.Signal(object)

    #: Signal(Any) --
    _valueFromWidget = QtCore.Signal(object)

    def __init__(self, parameter: Parameter, parent=None,
                 additionalWidgets: Optional[List[QtWidgets.QWidget]] = []):

        super().__init__(parent)

        self.setAutoFillBackground(False)

        self._parameter = parameter
        self._getMethod = lambda: None
        self._setMethod = lambda x: None

        layout = QtWidgets.QGridLayout(self)
        self.getButton = QtWidgets.QPushButton(QtGui.QIcon(":/icons/refresh.svg"),
                                               "", parent=self)
        self.getButton.pressed.connect(self.setWidgetFromParameter)
        keepSmallHorizontally(self.getButton)
        layout.addWidget(self.getButton, 0, 1)

        self.setButton = SetButton(QtGui.QIcon(":/icons/set.svg"), "", parent=self)
        keepSmallHorizontally(self.setButton)
        layout.addWidget(self.setButton, 0, 2)

        self.alertWidget = AlertLabel(self)
        layout.addWidget(self.alertWidget, 0, 3)

        # an input field will only be created if we have a set method.
        if hasattr(parameter, 'set'):

            self.parameterSet.connect(lambda x: self.setButton.setPending(False))
            self.parameterSet.connect(lambda x: self.alertWidget.clearAlert())
            self.parameterPending.connect(lambda x: self.setButton.setPending(True))
            self.parameterSetError.connect(self.alertWidget.setAlert)
            self.setButton.pressed.connect(self.getAndEmitValueFromWidget)

            # depending on the validator of the parameter, we'll create a fitting
            # input widget
            if False:
                pass
            else:
                self.paramWidget = AnyInput(self)
                self.paramWidget.setValue(parameter())
                self.paramWidget.inputChanged.connect(lambda x: self.setPending(x))
                self._getMethod = self.paramWidget.value
                self._setMethod = self.paramWidget.setValue

            self._valueFromWidget.connect(self.setParameter)

        # if we have no set method, then it'll be read-only
        else:
            self.setButton.setDisabled(True)
            self.paramWidget = QtWidgets.QLabel(self)
            self._setMethod = lambda x: self.paramWidget.setText(str(x))

        layout.addWidget(self.paramWidget, 0, 0)

        for i, w in enumerate(additionalWidgets):
            layout.addWidget(w, 0, 4+i)

        layout.setContentsMargins(1, 1, 1, 1)
        self.setLayout(layout)

    @QtCore.Slot(object)
    def setParameter(self, value: Any):
        try:
            self._parameter.set(value)
        except TypeError as e:
            self.parameterSetError.emit(e.args[0])
            return

        self.parameterSet.emit(value)

    @QtCore.Slot(object)
    def setPending(self, value: Any):
        self.parameterPending.emit(value)

    @QtCore.Slot()
    def getAndEmitValueFromWidget(self):
        self._valueFromWidget.emit(self._getMethod())

    @QtCore.Slot()
    def setWidgetFromParameter(self):
        val = self._parameter.get()
        self._setMethod(val)
        self.parameterSet.emit(val)


# ----------------------------------------------------------------------------
# custom (input) widgets

class SetButton(QtWidgets.QPushButton):

    @QtCore.Slot(bool)
    def setPending(self, isPending: bool):
        if isPending:
            self.setStyleSheet("SetButton { background-color: orange }")
        else:
            self.setStyleSheet("SetButton {}")


class AlertLabel(QtWidgets.QLabel):

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None):
        super().__init__(parent)
        pix = QtGui.QIcon(":/icons/no-alert.svg").pixmap(16, 16)
        self.setPixmap(pix)
        self.setToolTip('no alerts')

    @QtCore.Slot(str)
    def setAlert(self, message: str):
        pix = QtGui.QIcon(":/icons/red-alert.svg").pixmap(16, 16)
        self.setPixmap(pix)
        self.setToolTip(message)

    @QtCore.Slot()
    def clearAlert(self):
        pix = QtGui.QIcon(":/icons/no-alert.svg").pixmap(16, 16)
        self.setPixmap(pix)
        self.setToolTip('no alerts')


class AnyInput(QtWidgets.QWidget):

    #: Signal(str) --
    #: emitted when the input field is changed, argument is the new value.
    inputChanged = QtCore.Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)

        self.input = QtWidgets.QLineEdit()
        self.input.textEdited.connect(self._processTextEdited)

        self.doEval = QtWidgets.QPushButton(
            QtGui.QIcon(":/icons/python.svg"), "", parent=self,
        )
        self.doEval.setCheckable(True)
        self.doEval.setChecked(True)
        self.doEval.setToolTip("Evaluate input as python expression.\n"
                               "If evaluation fails, treat as string.")
        keepSmallHorizontally(self.doEval)

        layout = QtWidgets.QHBoxLayout(self)
        layout.addWidget(self.input)
        layout.addWidget(self.doEval)

        layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(layout)

        self.setStyleSheet("""
QPushButton:checked { background-color: palegreen }
""")

    def value(self):
        if self.doEval.isChecked():
            try:
                ret = eval(self.input.text())
            except Exception:
                ret = self.input.text()
            return ret
        else:
            return self.input.text()

    def setValue(self, val: Any):
        self.input.setText(str(val))

    @QtCore.Slot(str)
    def _processTextEdited(self, val: str):
        self.inputChanged.emit(val)

    def resetStyle(self):
        pass


# ----------------------------------------------------------------------------
# Tools

def parameterDialog(parameter: Parameter):
    def set(x):
        print(f'parameter set to: {x}')

    def pending(x):
        print(f'parameter value pending: {x}')

    pw = ParameterWidget(parameter)
    pw.parameterSet.connect(set)
    pw.parameterPending.connect(pending)

    dg = QtWidgets.QDialog()
    dg.setWindowTitle(parameter.label)
    lay = QtWidgets.QVBoxLayout(dg)
    lay.addWidget(pw)
    lay.setContentsMargins(0, 0, 0, 0)
    dg.setLayout(lay)
    dg.show()
    return dg


