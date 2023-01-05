import logging
import math
import numbers
from typing import Any, Optional, List

from qcodes import Parameter

from . import keepSmallHorizontally
from .misc import AlertLabel
from .. import QtWidgets, QtCore, QtGui, resource
from ..params import ParameterTypes, paramTypeFromVals

logger = logging.getLogger(__name__)


# TODO: do all styling with a global style sheet


class ParameterWidget(QtWidgets.QWidget):
    """A widget that allows editing and/or displaying a parameter value."""

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

        self.setAutoFillBackground(True)

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
            ptype = paramTypeFromVals(parameter.vals)
            vals = parameter.vals

            if ptype is ParameterTypes.integer:
                self.paramWidget = QtWidgets.QSpinBox(self)
                self.paramWidget.setMinimum(
                    -int(1e10) if not math.isfinite(vals._min_value) or
                                  abs(vals._min_value) > 1e10 else vals._min_value
                )
                self.paramWidget.setMaximum(
                    int(1e10) if not math.isfinite(vals._max_value) or
                                 abs(vals._max_value) > 1e10 else vals._max_value
                )
                self.paramWidget.setValue(parameter())
                self.paramWidget.valueChanged.connect(self.setPending)
                self._getMethod = self.paramWidget.value
                self._setMethod = self.paramWidget.setValue

            elif ptype is ParameterTypes.numeric or ptype is ParameterTypes.complex:
                self.paramWidget = NumberInput(self)
                self.paramWidget.setValue(parameter())
                self.paramWidget.textChanged.connect(self.setPending)
                self._getMethod = self.paramWidget.value
                self._setMethod = self.paramWidget.setValue

            elif ptype is ParameterTypes.string:
                self.paramWidget = QtWidgets.QLineEdit(self)
                self.paramWidget.setText(parameter())
                self.paramWidget.textChanged.connect(self.setPending)
                self._getMethod = self.paramWidget.text
                self._setMethod = self.paramWidget.setText

            elif ptype is ParameterTypes.bool:
                self.paramWidget = QtWidgets.QCheckBox(self)
                self.paramWidget.setChecked(parameter())
                self.paramWidget.toggled.connect(self.setPending)
                self._getMethod = self.paramWidget.isChecked
                self._setMethod = self.paramWidget.setChecked

            else:  # means it's any, or an unsupported type.
                self.paramWidget = AnyInput(self)
                self.paramWidget.setValue(parameter())
                self.paramWidget.inputChanged.connect(self.setPending)
                self.paramWidget.input.returnPressed.connect(self.onEnterPressed)
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
            layout.addWidget(w, 0, 4 + i)

        for i in range(layout.columnCount()):
            if i == 0:
                layout.setColumnStretch(i, 1)
            else:
                layout.setColumnStretch(i, 0)

        layout.setContentsMargins(1, 1, 1, 1)
        self.setLayout(layout)

    @QtCore.Slot()
    def onEnterPressed(self):
        """Activates the setButton when the input is selected and enter is pressed."""
        self.setButton.click()
        self.paramWidget.input.deselect()
        self.setButton.setFocus()


    def setParameter(self, value: Any):
        try:
            self._parameter.set(value)
        except Exception as e:
            self.parameterSetError.emit(f"Could not set parameter, raised {type(e)}:"
                                        f" {e.args}")
            return

        self.parameterSet.emit(value)

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
            except Exception as e:
                ret = self.input.text()
            return ret
        else:
            return self.input.text()

    def setValue(self, val: Any):
        self.input.setText(str(val))

    @QtCore.Slot(str)
    def _processTextEdited(self, val: str):
        self.inputChanged.emit(val)


class NumberInput(QtWidgets.QLineEdit):
    """A text edit widget that checks whether its input can be read as a number."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.textChanged.connect(self.checkIfNumber)

    def checkIfNumber(self, value: str):
        try:
            val = eval(value)
        except:
            val = None

        if not isinstance(val, numbers.Number):
            self.setStyleSheet("""
            NumberInput { background-color: pink }
            """)
        else:
            self.setStyleSheet("""
            NumberInput { }
            """)

    def value(self):
        try:
            value = eval(self.text())
        except:
            return None
        if isinstance(value, numbers.Number):
            return value
        else:
            return None

    def setValue(self, value: numbers.Number):
        self.setText(str(value))


class SetButton(QtWidgets.QPushButton):

    @QtCore.Slot(bool)
    def setPending(self, isPending: bool):
        if isPending:
            self.setStyleSheet("SetButton { background-color: orange }")
        else:
            self.setStyleSheet("SetButton {}")
