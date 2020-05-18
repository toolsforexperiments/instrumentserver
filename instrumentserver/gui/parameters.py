from typing import Any
import logging

from qcodes import Parameter

from .. import QtWidgets, QtCore, QtGui, resource
from .. import log


logger = logging.getLogger(__name__)


class ParameterWidget(QtWidgets.QWidget):
    """A widget that allows editing and/or displaying a parameter value."""

    # TODO: a method to show that there's a return value of some sort

    #: Signal(Any) --
    #: emitted when the parameter was set successfully
    parameterSet = QtCore.Signal(object)

    #: Signal(Any) --
    #: emitted when the parameter value is pending
    parameterPending = QtCore.Signal(object)

    #: Signal(Any) --
    _valueFromWidget = QtCore.Signal(object)

    def __init__(self, parameter: Parameter, parent=None):
        super().__init__(parent)

        self._parameter = parameter
        self._getMethod = lambda: None
        self._setMethod = lambda x: None

        layout = QtWidgets.QGridLayout(self)
        self.getButton = QtWidgets.QPushButton(QtGui.QIcon(":/icons/refresh.svg"),
                                               "", parent=self)
        self.getButton.pressed.connect(self.setWidgetFromParameter)
        layout.addWidget(self.getButton, 0, 1)

        # an input field will only be created if we have a set method.
        if hasattr(parameter, 'set'):

            self.setButton = SetButton(QtGui.QIcon(":/icons/set.svg"), "", parent=self)
            self.parameterSet.connect(lambda x: self.setButton.setPending(False))
            self.parameterPending.connect(lambda x: self.setButton.setPending(True))
            self.setButton.pressed.connect(self.getAndEmitValueFromWidget)
            layout.addWidget(self.setButton, 0, 2)

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

            layout.addWidget(self.paramWidget, 0, 0)

            self._valueFromWidget.connect(self.setParameter)

        # if we have no set method, then it'll be read-only
        else:
            pass

        self.setLayout(layout)

    @QtCore.Slot(object)
    def setParameter(self, value: Any):
        self._parameter.set(value)
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


class AnyInput(QtWidgets.QWidget):

    #: Signal(str) --
    #: emitted when the input field is changed, argument is the new value.
    inputChanged = QtCore.Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)

        self.input = QtWidgets.QLineEdit()
        self.input.textEdited.connect(self._processTextEdited)

        self.doEval = QtWidgets.QCheckBox()
        self.doEval.setCheckState(QtCore.Qt.Checked)
        doEvalLabel = QtWidgets.QLabel('Eval')
        doEvalLabel.setSizePolicy(
            QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Fixed,
                                  QtWidgets.QSizePolicy.Minimum)
        )

        layout = QtWidgets.QHBoxLayout(self)
        layout.addWidget(self.input)
        layout.addWidget(doEvalLabel)
        layout.addWidget(self.doEval)

        layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(layout)

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


