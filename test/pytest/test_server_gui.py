import json
from pathlib import Path

from instrumentserver import QtCore
from instrumentserver.gui.instruments import GenericInstrument
from instrumentserver.server.application import startServerGuiApplication


def test_saving_button(qtbot):
    correct_file_dict = {
        "rr.bandwidth": 10000.0,
        "rr.data": None,
        "rr.frequency": None,
        "rr.input_attenuation": 70,
        "rr.noise_temperature": 4.0,
        "rr.npoints": 1601,
        "rr.power": -100,
        "rr.resonator_frequency": 5000000000.0,
        "rr.resonator_linewidth": 1000000.0,
        "rr.start_frequency": 20000.0,
        "rr.stop_frequency": 20000000000.0
    }


    window = startServerGuiApplication()
    rr = window.client.find_or_create_instrument('rr',
                                                 'instrumentserver.testing.dummy_instruments.rf.ResonatorResponse')

    qtbot.addWidget(window)
    saving_widget = window.toolBar.widgetForAction(window.saveParamsAction)
    qtbot.mouseClick(saving_widget, QtCore.Qt.LeftButton)

    file_path = Path(window._paramValuesFile)
    try:
        assert file_path.is_file()
        with open(str(file_path), 'r') as f:
            loaded_file = json.load(f)
        assert correct_file_dict == loaded_file

    finally:
        file_path.unlink(missing_ok=True)


def test_loading_button(qtbot):
    correct_file_dict = {
        "dummy.A.ch0": 0,
        "dummy.A.ch1": 1,
        "dummy.B.ch0": 0,
        "dummy.B.ch1": 1,
        "dummy.C.ch0": 0,
        "dummy.C.ch1": 1,
        "dummy.param0": 1,
        "dummy.param1": 1,
    }

    window = startServerGuiApplication()

    file_path = Path(window._paramValuesFile)

    with open(str(file_path), 'w+') as f:
        json.dump(correct_file_dict, f)

    dummy = window.client.find_or_create_instrument('dummy',
                                                    'instrumentserver.testing.dummy_instruments.generic.DummyInstrumentWithSubmodule')

    qtbot.addWidget(window)
    loading_widget = window.toolBar.widgetForAction(window.loadParamsAction)
    qtbot.mouseClick(loading_widget, QtCore.Qt.LeftButton)
    try:
        assert dummy.param0() == 1
        assert dummy.param1() == 1

    finally:
        file_path.unlink(missing_ok=True)


def test_refresh_button(qtbot):
    window = startServerGuiApplication()
    qtbot.addWidget(window)

    assert window.stationList.topLevelItemCount() == 0

    dummy = window.client.find_or_create_instrument('dummy',
                                                    'instrumentserver.testing.dummy_instruments.generic.DummyInstrumentWithSubmodule')

    refresh_widget = window.toolBar.widgetForAction(window.refreshStationAction)
    qtbot.mouseClick(refresh_widget, QtCore.Qt.LeftButton)

    assert window.stationList.topLevelItemCount() == 1


def test_clicking_an_item(qtbot):
    # If there is an exception raise, it will not reach the assert True statement

    window = startServerGuiApplication()
    qtbot.addWidget(window)

    assert window.stationList.topLevelItemCount() == 0

    dummy = window.client.find_or_create_instrument('dummy',
                                                    'instrumentserver.testing.dummy_instruments.generic.DummyInstrumentWithSubmodule')

    window.refreshStationAction.trigger()
    item = window.stationList.findItems('dummy', QtCore.Qt.MatchExactly | QtCore.Qt.MatchRecursive, 0)
    widget = item[0].treeWidget()
    qtbot.mouseClick(widget, QtCore.Qt.LeftButton)

    assert True


def test_opening_new_tab_generic_object(qtbot):
    window = startServerGuiApplication()
    qtbot.addWidget(window)

    dummy = window.client.find_or_create_instrument('dummy',
                                                    'instrumentserver.testing.dummy_instruments.generic.DummyInstrumentWithSubmodule')

    window.refreshStationAction.trigger()
    item = window.stationList.findItems('dummy', QtCore.Qt.MatchExactly | QtCore.Qt.MatchRecursive, 0)

    # Manually triggering the tab opening since qtbot refuses to double-click an item
    window.addInstrumentTab(item[0], 0)

    assert 'dummy' in window.instrumentTabsOpen

    assert isinstance(window.instrumentTabsOpen['dummy'], GenericInstrument)



