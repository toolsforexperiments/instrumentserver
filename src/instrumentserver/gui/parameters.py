import logging
import numbers
import re
from typing import Any, Callable, List, Optional, Tuple

from qcodes import Parameter

from .. import QtCore, QtGui, QtWidgets
from ..params import ParameterTypes, paramTypeFromVals
from . import keepSmallHorizontally
from .misc import AlertLabel
from .undo_commands import SetParameterCommand, ToggleEvalCommand

logger = logging.getLogger(__name__)


# TODO: do all styling with a global style sheet

FLOAT_PRECISION = 10  # The maximum number of significant digits for float numbers


def float_formater(val: Any) -> str:
    """
    For displaying float numbers with scientific notation.
    """
    if isinstance(val, float):
        if abs(val) > 1e5 or (0 < abs(val) < 1e-4):
            formatted = f"{val:.{FLOAT_PRECISION - 1}g}"
            # remove leading 0 in exponent
            formatted = re.sub(r"e([+-])0(\d+)", r"e\1\2", formatted)
            return formatted
    return str(val)


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

    def __init__(
        self,
        parameter: Parameter,
        parent: Optional[QtWidgets.QWidget] = None,
        additionalWidgets: Optional[List[QtWidgets.QWidget]] = None,
    ) -> None:

        super().__init__(parent)

        self.setAutoFillBackground(True)

        self._parameter = parameter
        self._getMethod: Callable[[], Optional[Any]] = lambda: None
        self._setMethod = lambda x: None
        self.undoStack: Any = None
        self._suppress_command_push: bool = False
        self._suppress_eval_push: bool = False
        self._full_name: Any = None
        self._delegate: Any = None

        layout = QtWidgets.QGridLayout(self)
        self.getButton = QtWidgets.QPushButton(
            QtGui.QIcon(":/icons/refresh.svg"), "", parent=self
        )
        self.getButton.pressed.connect(self.setWidgetFromParameter)
        keepSmallHorizontally(self.getButton)
        layout.addWidget(self.getButton, 0, 1)

        self.setButton = SetButton(QtGui.QIcon(":/icons/set.svg"), "", parent=self)
        keepSmallHorizontally(self.setButton)
        layout.addWidget(self.setButton, 0, 2)

        self.alertWidget = AlertLabel(self)
        layout.addWidget(self.alertWidget, 0, 3)

        # an input field will only be created if we have a set method.
        if hasattr(parameter, "set"):
            self.parameterSet.connect(lambda x: self.setButton.setPending(False))
            self.parameterSet.connect(lambda x: self.alertWidget.clearAlert())
            self.parameterPending.connect(lambda x: self.setButton.setPending(True))
            self.parameterSetError.connect(self.alertWidget.setAlert)
            self.setButton.pressed.connect(self.getAndEmitValueFromWidget)

            # depending on the validator of the parameter, we'll create a fitting
            # input widget
            ptype = paramTypeFromVals(parameter.vals)
            self.paramWidget: (
                NumberInput
                | AnyInput
                | QtWidgets.QLineEdit
                | QtWidgets.QCheckBox
                | QtWidgets.QLabel
            )

            # FIXME: Currently blueprints don't pass validators meaning that we will never reach any of these if statements.
            #  This should get uncommented when the blueprints are fixed.
            # if ptype is ParameterTypes.integer:
            #     self.paramWidget = QtWidgets.QSpinBox(self)
            #     self.paramWidget.setMinimum(
            #         -int(1e10) if not math.isfinite(vals._min_value) or
            #                       abs(vals._min_value) > 1e10 else vals._min_value
            #     )
            #     self.paramWidget.setMaximum(
            #         int(1e10) if not math.isfinite(vals._max_value) or
            #                      abs(vals._max_value) > 1e10 else vals._max_value
            #     )
            #     self.paramWidget.setValue(parameter())
            #     self.paramWidget.valueChanged.connect(self.setPending)
            #     self._getMethod = self.paramWidget.value
            #     self._setMethod = self.paramWidget.setValue

            if ptype is ParameterTypes.numeric or ptype is ParameterTypes.complex:
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
                self.paramWidget.input.returnPressed.connect(self.onReturnPressed)
                self.paramWidget.doEval.toggled.connect(self._onDoEvalToggled)
                self._getMethod = self.paramWidget.value
                self._setMethod = self.paramWidget.setValue

            self._valueFromWidget.connect(self.setParameter)

        # if we have no set method, then it'll be read-only
        else:
            self.setButton.setDisabled(True)
            self.paramWidget = QtWidgets.QLabel(self)
            self._setMethod = lambda x: (
                self.paramWidget.setText(str(x))
                if isinstance(self.paramWidget, QtWidgets.QLabel)
                else None
            )
            try:  # also do immediate update for read-only params, as what we do for the editable parameters above.
                self._setMethod(parameter())
            except Exception as e:
                logger.warning(
                    f"Error when setting parameter {parameter}: {e}", exc_info=True
                )

        layout.addWidget(self.paramWidget, 0, 0)
        additionalWidgets = additionalWidgets or []
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
    def onReturnPressed(self) -> None:
        """Activates the setButton when the input is selected and enter is pressed."""
        self.setButton.click()
        self.paramWidget.input.deselect()
        self.setButton.setFocus()

    def setParameter(self, value: Any) -> None:
        if not self._suppress_command_push and self.undoStack is not None:
            try:
                old_value = self._parameter.get()
            except Exception:
                old_value = None

        try:
            self._parameter.set(value)
            actual = self._parameter.get()
            if actual != value:
                self.parameterSetError.emit(
                    f"Parameter rejected value {value!r} (current: {actual!r})"
                )
                return
        except Exception as e:
            self.parameterSetError.emit(
                f"Could not set parameter, raised {type(e)}: {e.args}"
            )
            return

        if not self._suppress_command_push and self.undoStack is not None:
            self.undoStack.push(
                SetParameterCommand(
                    self._parameter, self._full_name, self._delegate, old_value, value
                )
            )

        self.parameterSet.emit(value)

    def setPending(self, value: Any) -> None:
        self.parameterPending.emit(value)

    @QtCore.Slot()
    def getAndEmitValueFromWidget(self) -> None:
        self._valueFromWidget.emit(self._getMethod())

    @QtCore.Slot()
    def setWidgetFromParameter(self) -> None:
        val = self._parameter.get()
        self._setMethod(val)
        self.parameterSet.emit(val)

    @QtCore.Slot(bool)
    def _onDoEvalToggled(self, _: bool) -> None:
        if not self._suppress_eval_push and self.undoStack is not None:
            self.undoStack.push(ToggleEvalCommand(self._full_name, self._delegate))


class AnyInput(QtWidgets.QWidget):
    #: Signal(str) --
    #: emitted when the input field is changed, argument is the new value.
    inputChanged = QtCore.Signal(str)

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)

        self.input = QtWidgets.QLineEdit()
        self.input.textEdited.connect(self._processTextEdited)

        self.doEval = QtWidgets.QPushButton(
            QtGui.QIcon(":/icons/python.svg"),
            "",
            parent=self,
        )
        self.doEval.setCheckable(True)
        self.doEval.setChecked(True)
        self.doEval.setToolTip(
            "Evaluate input as python expression.\n"
            "If evaluation fails, treat as string."
        )
        keepSmallHorizontally(self.doEval)

        layout = QtWidgets.QHBoxLayout(self)
        layout.addWidget(self.input)
        layout.addWidget(self.doEval)
        layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(layout)

        self.setStyleSheet("""
QPushButton:checked { background-color: palegreen }
""")

    def value(self) -> Any:
        if self.doEval.isChecked():
            try:
                ret = eval(self.input.text())
            except Exception:
                ret = self.input.text()
            return ret
        else:
            return self.input.text()

    def setValue(self, val: Any) -> None:
        try:
            self.input.setText(float_formater(val))
        except RuntimeError as e:
            logger.debug(
                f"Could not set value {val} in AnyInput element does not exists, raised {type(e)}: {e.args}"
            )

    @QtCore.Slot(str)
    def _processTextEdited(self, val: str) -> None:
        self.inputChanged.emit(val)


class NumberInput(QtWidgets.QLineEdit):
    """A text edit widget that checks whether its input can be read as a number."""

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self.textChanged.connect(self.checkIfNumber)

    def checkIfNumber(self, value: str) -> None:
        try:
            val = eval(value)
        except Exception:
            val = None

        if not isinstance(val, numbers.Number):
            self.setStyleSheet("""
            NumberInput { background-color: pink }
            """)
        else:
            self.setStyleSheet("""
            NumberInput { }
            """)

    def value(self) -> Optional[numbers.Number]:
        try:
            value = eval(self.text())
        except Exception:
            return None
        if isinstance(value, numbers.Number):
            return value
        else:
            return None

    def setValue(self, value: numbers.Number) -> None:
        try:
            self.setText(float_formater(value))
        except RuntimeError as e:
            logger.debug(
                f"Could not set value {value} in NumberInput, raised {type(e)}: {e.args}"
            )


class AnyInputForMethod(AnyInput):
    """
    Implementation of AnyInput that can process arguments and keyword arguments to use for methods.
    You can add multiple arguments if they are separated by a comma. If the '=' is present in any argument, it will
    be treated like a keyword argument with the string in front of the equal sign as the key, and the evaluated value.

    All arguments and keyword arguments are evaluated if the doEval button is checked, if not everything is treated like
    a long string.
    """

    def value(self) -> Tuple[Any, Any]:
        if self.doEval.isChecked():
            # If '=' is present we need to separate the keyword from the value
            # If ',' is present we have more than one argument.
            if "=" in self.input.text() or "," in self.input.text():
                rawArgs = self.input.text().split(",")
                args = []
                kwargs = {}
                for x in rawArgs:
                    if "=" in x:
                        key, value = x.split("=")
                        key = key.replace(" ", "")
                        kwargs[key] = eval(value)
                    else:
                        args.append(eval(x))
                return tuple(args), kwargs
            else:
                return super().value(), None

        return self.input.text(), None


class SetButton(QtWidgets.QPushButton):
    @QtCore.Slot(bool)
    def setPending(self, isPending: bool) -> None:
        if isPending:
            self.setStyleSheet("SetButton { background-color: orange }")
        else:
            self.setStyleSheet("SetButton {}")
