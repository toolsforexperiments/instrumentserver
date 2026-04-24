"""Tests for ClientStation and ClientStationGui."""


import pytest

from instrumentserver.client.proxy import ClientStation

DUMMY_CLASS = (
    "instrumentserver.testing.dummy_instruments.generic.DummyInstrumentWithSubmodule"
)


# ---------------------------------------------------------------------------
# ClientStation (no GUI)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def client_station(start_server):
    station = ClientStation(host="localhost", port=5555)
    yield station
    station.disconnect()


def test_client_station_creates_instruments(client_station):
    client_station.find_or_create_instrument("cs_dummy", DUMMY_CLASS)
    assert "cs_dummy" in client_station.instruments


def test_client_station_get_parameters(client_station):
    client_station.find_or_create_instrument("cs_dummy", DUMMY_CLASS)
    params = client_station.get_parameters()
    assert isinstance(params, dict)
    assert "cs_dummy" in params


def test_client_station_set_parameters(client_station):
    ins = client_station.find_or_create_instrument("cs_dummy", DUMMY_CLASS)
    ins.param0(0)
    client_station.set_parameters({"cs_dummy": {"param0": 1}})
    assert ins.param0() == 1


def test_client_station_save_load_parameters(tmp_path, client_station):
    ins = client_station.find_or_create_instrument("cs_dummy", DUMMY_CLASS)
    ins.param0(1)

    file_path = str(tmp_path / "params.json")
    client_station.save_parameters(file_path)

    # Mutate the value
    ins.param0(0)
    assert ins.param0() == 0

    # Load back
    client_station.load_parameters(file_path)
    assert ins.param0() == 1


def test_client_station_get_instrument(client_station):
    client_station.find_or_create_instrument("cs_dummy", DUMMY_CLASS)
    retrieved = client_station.get_instrument("cs_dummy")
    assert retrieved is not None
    assert retrieved.name == "cs_dummy"


def test_client_station_subscript_access(client_station):
    client_station.find_or_create_instrument("cs_dummy", DUMMY_CLASS)
    assert client_station["cs_dummy"] is client_station.instruments["cs_dummy"]


# ---------------------------------------------------------------------------
# ClientStationGui
# ---------------------------------------------------------------------------


def test_client_station_gui_opens(qtbot, start_server):
    from instrumentserver.client.application import ClientStationGui

    station = ClientStation(host="localhost", port=5555)
    window = ClientStationGui(station)
    qtbot.addWidget(window)
    try:
        assert window is not None
    finally:
        window.close()
        station.disconnect()


def test_client_station_gui_has_three_tabs(qtbot, start_server):
    from instrumentserver.client.application import ClientStationGui

    station = ClientStation(host="localhost", port=5555)
    window = ClientStationGui(station)
    qtbot.addWidget(window)
    try:
        tab_texts = [window.tabs.tabText(i) for i in range(window.tabs.count())]
        assert "Station" in tab_texts
        assert "Log" in tab_texts
        assert "Server" in tab_texts
    finally:
        window.close()
        station.disconnect()


def test_client_station_gui_server_widget_shows_host_port(qtbot, start_server):
    from instrumentserver.client.application import ClientStationGui

    station = ClientStation(host="localhost", port=5555)
    window = ClientStationGui(station)
    qtbot.addWidget(window)
    try:
        assert window.server_widget.host.text() == "localhost"
        assert window.server_widget.port.text() == "5555"
    finally:
        window.close()
        station.disconnect()


def test_client_station_gui_station_list_populated(qtbot, start_server):
    from instrumentserver.client.application import ClientStationGui

    station = ClientStation(host="localhost", port=5555)
    station.find_or_create_instrument("gui_cs_dummy", DUMMY_CLASS)
    window = ClientStationGui(station)
    qtbot.addWidget(window)
    try:
        assert window.stationList.topLevelItemCount() >= 1
    finally:
        window.close()
        station.disconnect()


def test_client_station_gui_open_instrument_tab(qtbot, start_server):
    from instrumentserver import QtCore
    from instrumentserver.client.application import ClientStationGui
    from instrumentserver.gui.instruments import GenericInstrument

    station = ClientStation(host="localhost", port=5555)
    station.find_or_create_instrument("gui_cs_dummy2", DUMMY_CLASS)
    window = ClientStationGui(station)
    qtbot.addWidget(window)
    try:
        items = window.stationList.findItems(
            "gui_cs_dummy2", QtCore.Qt.MatchExactly | QtCore.Qt.MatchRecursive, 0
        )
        assert len(items) > 0

        window.openInstrumentTab(items[0], 0)
        assert "gui_cs_dummy2" in window.instrumentTabsOpen
        assert isinstance(window.instrumentTabsOpen["gui_cs_dummy2"], GenericInstrument)
    finally:
        window.close()
        station.disconnect()
