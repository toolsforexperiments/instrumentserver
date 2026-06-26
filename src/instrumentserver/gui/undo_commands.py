from typing import Any, Tuple

from instrumentserver import QtCore, QtGui, QtWidgets
from instrumentserver.helpers import nestedAttributeFromString


class SetParameterCommand(QtWidgets.QUndoCommand):
    def __init__(
        self, param: Any, name: str, delegate: Any, old_val: Any, new_val: Any
    ) -> None:
        super().__init__(f"Set {param.name}")
        self._param = param
        self._name = name
        self._delegate = delegate
        self._old = old_val
        self._new = new_val
        self._first = True

    def _get_widget(self) -> Any:
        if hasattr(self._delegate, "parameters"):
            return self._delegate.parameters.get(self._name)
        return None

    def _apply(self, value: Any) -> None:
        widget = self._get_widget()
        if widget is None:
            return
        widget._suppress_command_push = True
        try:
            self._param.set(value)
            actual = self._param.get()
            if actual != value:
                widget.parameterSetError.emit(
                    f"Could not set parameter: value is {actual!r}, not {value!r}"
                )
                widget._setMethod(actual)
            else:
                widget._setMethod(value)
                widget.parameterSet.emit(value)
        except Exception as e:
            widget.parameterSetError.emit(
                f"Could not set parameter, raised {type(e)}: {e.args}"
            )
        finally:
            widget._suppress_command_push = False

    def undo(self) -> None:
        self._apply(self._old)

    def redo(self) -> None:
        if self._first:
            self._first = False
            return
        self._apply(self._new)


def _restore_star_trash(item: Any, star: bool, trash: bool) -> None:
    item.star = star
    item.trash = trash
    if star:
        item.setIcon(QtGui.QIcon(":/icons/star.svg"))
    elif trash:
        item.setIcon(QtGui.QIcon(":/icons/trash.svg"))
    else:
        item.setIcon(QtGui.QIcon())


class ToggleStarTrashCommand(QtWidgets.QUndoCommand):
    def __init__(self, item: Any, model: Any, mode: str) -> None:
        super().__init__(f"Toggle {mode} {item.name}")
        self._name = item.name
        self._model = model
        self._mode = mode
        self._old_star = item.star
        self._old_trash = item.trash
        self._first = True

    def _get_item(self) -> Any:
        items = self._model.findItems(
            self._name,
            QtCore.Qt.MatchFlag.MatchExactly | QtCore.Qt.MatchFlag.MatchRecursive,
            0,
        )
        return items[0] if items else None

    def undo(self) -> None:
        item = self._get_item()
        if item is not None:
            _restore_star_trash(item, self._old_star, self._old_trash)

    def redo(self) -> None:
        if self._first:
            self._first = False
            return
        item = self._get_item()
        if item is not None:
            if self._mode == "star":
                self._model.onItemStarToggle(item)
            else:
                self._model.onItemTrashToggle(item)


class ToggleEvalCommand(QtWidgets.QUndoCommand):
    def __init__(self, name: str, delegate: Any) -> None:
        super().__init__("Toggle eval")
        self._name = name
        self._delegate = delegate
        self._first = True

    def _get_owner_and_eval(self) -> Tuple[Any, Any]:
        if hasattr(self._delegate, "parameters"):
            owner = self._delegate.parameters.get(self._name)
            if (
                owner is not None
                and hasattr(owner, "paramWidget")
                and hasattr(owner.paramWidget, "doEval")
            ):
                return owner, owner.paramWidget.doEval
        if hasattr(self._delegate, "methods"):
            owner = self._delegate.methods.get(self._name)
            if owner is not None and hasattr(owner, "anyInput"):
                return owner, owner.anyInput.doEval
        return None, None

    def _apply(self) -> None:
        owner, eval_widget = self._get_owner_and_eval()
        if owner is None or eval_widget is None:
            return
        owner._suppress_eval_push = True
        try:
            eval_widget.toggle()
        finally:
            owner._suppress_eval_push = False

    def undo(self) -> None:
        self._apply()

    def redo(self) -> None:
        if self._first:
            self._first = False
            return
        self._apply()


class DeleteParameterCommand(QtWidgets.QUndoCommand):
    """Undo/redo a parameter deletion in ParameterManagerGui."""

    def __init__(
        self,
        parent_gui: Any,
        full_name: str,
        value: Any,
        unit: str,
        star: bool,
        trash: bool,
    ) -> None:
        super().__init__(f"Delete {full_name}")
        self._gui = parent_gui
        self._full_name = full_name
        self._value = value
        self._unit = unit
        self._star = star
        self._trash = trash
        widget = parent_gui.view.delegate.parameters.get(full_name)
        if (
            widget is not None
            and hasattr(widget, "paramWidget")
            and hasattr(widget.paramWidget, "doEval")
        ):
            self._doEval: bool = widget.paramWidget.doEval.isChecked()
        else:
            self._doEval = True

    def undo(self) -> None:
        self._gui.instrument.add_parameter(
            self._full_name, initial_value=self._value, unit=self._unit
        )
        param = nestedAttributeFromString(self._gui.instrument, self._full_name)
        item = self._gui.model.addItem(
            fullName=self._full_name,
            star=False,
            trash=False,
            element=param,
            unit=self._unit,
        )
        _restore_star_trash(item, self._star, self._trash)
        widget = self._gui.view.delegate.parameters.get(self._full_name)
        if (
            widget is not None
            and hasattr(widget, "paramWidget")
            and hasattr(widget.paramWidget, "doEval")
        ):
            widget._suppress_eval_push = True
            widget.paramWidget.doEval.setChecked(self._doEval)
            widget._suppress_eval_push = False

    def redo(self) -> None:
        if self._gui.instrument.has_param(self._full_name):
            self._gui.instrument.remove_parameter(self._full_name)
        self._gui.model.removeItem(self._full_name)
