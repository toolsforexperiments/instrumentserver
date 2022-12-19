import json
from pathlib import Path

from instrumentserver import QtCore
from instrumentserver.serialize import toParamDict
from instrumentserver.server.application import startServerGuiApplication


def test_saving_button(qtbot):
    window = startServerGuiApplication()
    dummy = window.client.find_or_create_instrument('dummy', 'instrumentserver.testing.dummy_instruments.generic.DummyInstrumentWithSubmodule')
    params = window.client.find_or_create_instrument('params', 'instrumentserver.params.ParameterManager')

    params.add_parameter('param0', initial_value=10, unit='m')
    params.add_parameter('param1', initial_value=11, unit='m')

    qtbot.addWidget(window)
    saving_widget = window.toolBar.widgetForAction(window.saveParamsAction)
    qtbot.mouseClick(saving_widget, QtCore.Qt.LeftButton)

    save_file_path = Path(window._paramValuesFile)
    assert save_file_path.is_file()

    param_dict = toParamDict(window.stationServer.station)
    with open(str(save_file_path), 'r') as f:
        loaded_file = json.load(f)
    assert param_dict == loaded_file

    save_file_path.unlink(missing_ok=True)








