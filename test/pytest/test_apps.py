"""Tests for instrumentserver/apps.py entry points.

Unit tests (no Qt, millisecond-fast) mock at the outermost call boundary:
  - instrumentserver.apps.server
  - instrumentserver.apps.serverWithGui
  - instrumentserver.apps.loadConfig

Integration tests (marked @pytest.mark.integration) spawn real subprocesses.
Run unit only: pytest test/pytest/test_apps.py -m "not integration" -v
Run integration: pytest test/pytest/test_apps.py -m "integration" -v
"""

import os
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

MINIMAL_CONFIG = """\
instruments:
  dummy:
    type: instrumentserver.testing.dummy_instruments.generic.DummyInstrumentWithSubmodule
"""


@pytest.fixture()
def config_file(tmp_path):
    p = tmp_path / "config.yml"
    p.write_text(MINIMAL_CONFIG)
    return str(p)


@pytest.fixture()
def fake_load_config():
    """Patch loadConfig to return a controlled 7-tuple (no polling)."""
    tf = tempfile.NamedTemporaryFile(delete=False, suffix=".tmp")
    station_file = tempfile.NamedTemporaryFile(delete=False, suffix=".yml", mode="w")
    station_file.write("")
    station_file.close()
    station_path = station_file.name

    def _fake(configPath):
        return (
            station_path,  # stationConfig
            {"instrument1": {}},  # serverConfig
            {},  # guiConfig
            {},  # shortcutConfig
            tf,  # tempFile
            {},  # pollingRates (empty → no polling thread)
            {},  # ipAddresses
        )

    with patch("instrumentserver.apps.loadConfig", side_effect=_fake) as mock_lc:
        yield mock_lc

    tf.close()
    Path(station_path).unlink(missing_ok=True)


@pytest.fixture()
def fake_load_config_polling():
    """Patch loadConfig to return a controlled 7-tuple (with polling rates)."""
    tf = tempfile.NamedTemporaryFile(delete=False, suffix=".tmp")
    station_file = tempfile.NamedTemporaryFile(delete=False, suffix=".yml", mode="w")
    station_file.write("")
    station_file.close()
    station_path = station_file.name

    def _fake(configPath):
        return (
            station_path,
            {"instrument1": {}},
            {},
            {},
            tf,
            {"dummy/param": 1.0},  # non-empty → polling thread
            {},
        )

    with patch("instrumentserver.apps.loadConfig", side_effect=_fake) as mock_lc:
        yield mock_lc

    tf.close()
    Path(station_path).unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Phase 1 — serverScript unit tests
# ---------------------------------------------------------------------------


def test_server_script_gui_default_no_config():
    """Case 1: default --gui, no -c → serverWithGui called, loadConfig NOT called."""
    sys.argv = ["instrumentserver"]
    with (
        patch("instrumentserver.apps.serverWithGui") as mock_gui,
        patch("instrumentserver.apps.server") as mock_srv,
        patch("instrumentserver.apps.loadConfig") as mock_lc,
    ):
        from instrumentserver.apps import serverScript

        serverScript()

    mock_gui.assert_called_once()
    mock_srv.assert_not_called()
    mock_lc.assert_not_called()

    kwargs = mock_gui.call_args.kwargs
    assert kwargs["serverConfig"] is None
    assert kwargs["stationConfig"] is None


def test_server_script_no_gui_no_config():
    """Case 2: --gui False, no -c → server called, loadConfig NOT called."""
    sys.argv = ["instrumentserver", "--gui", "False"]
    with (
        patch("instrumentserver.apps.serverWithGui") as mock_gui,
        patch("instrumentserver.apps.server") as mock_srv,
        patch("instrumentserver.apps.loadConfig") as mock_lc,
    ):
        from instrumentserver.apps import serverScript

        serverScript()

    mock_srv.assert_called_once()
    mock_gui.assert_not_called()
    mock_lc.assert_not_called()

    kwargs = mock_srv.call_args.kwargs
    assert kwargs["serverConfig"] is None
    assert kwargs["stationConfig"] is None


def test_server_script_gui_with_config(fake_load_config, config_file):
    """Case 3: default --gui, with -c → serverWithGui called with correct kwargs."""
    sys.argv = ["instrumentserver", "-c", config_file]
    with (
        patch("instrumentserver.apps.serverWithGui") as mock_gui,
        patch("instrumentserver.apps.server") as mock_srv,
    ):
        from instrumentserver.apps import serverScript

        serverScript()

    fake_load_config.assert_called_once_with(config_file)
    mock_gui.assert_called_once()
    mock_srv.assert_not_called()

    kwargs = mock_gui.call_args.kwargs
    assert kwargs["serverConfig"] == {"instrument1": {}}
    assert kwargs["shortcutConfig"] == {}
    assert kwargs["configPath"] == config_file


def test_server_script_no_gui_with_config(fake_load_config, config_file):
    """Case 4: --gui False, with -c → server called WITHOUT shortcutConfig/configPath.

    This test catches the bug where shortcutConfig and configPath were
    incorrectly forwarded to server() / startServer(), which does not accept them.
    """
    sys.argv = ["instrumentserver", "--gui", "False", "-c", config_file]
    with (
        patch("instrumentserver.apps.serverWithGui") as mock_gui,
        patch("instrumentserver.apps.server") as mock_srv,
    ):
        from instrumentserver.apps import serverScript

        serverScript()

    fake_load_config.assert_called_once_with(config_file)
    mock_srv.assert_called_once()
    mock_gui.assert_not_called()

    kwargs = mock_srv.call_args.kwargs
    assert kwargs["serverConfig"] == {"instrument1": {}}
    assert "shortcutConfig" not in kwargs, (
        "shortcutConfig must not be passed to server()"
    )
    assert "configPath" not in kwargs, "configPath must not be passed to server()"


def test_server_script_gui_with_polling(fake_load_config_polling, config_file):
    """Case 5: default --gui, with -c and polling rates → PollingWorker instantiated."""
    sys.argv = ["instrumentserver", "-c", config_file]
    with (
        patch("instrumentserver.apps.serverWithGui") as mock_gui,
        patch("instrumentserver.apps.server") as mock_srv,
        patch("instrumentserver.apps.PollingWorker") as mock_pw,
        patch("instrumentserver.apps.QtCore.QThread") as mock_qt,
    ):
        from instrumentserver.apps import serverScript

        serverScript()

    mock_gui.assert_called_once()
    mock_srv.assert_not_called()
    mock_pw.assert_called_once_with(pollingRates={"dummy/param": 1.0})
    mock_qt.assert_called_once()

    kwargs = mock_gui.call_args.kwargs
    assert kwargs["pollingThread"] is not None


def test_server_script_no_gui_with_polling(fake_load_config_polling, config_file):
    """Case 6: --gui False, with -c and polling rates → PollingWorker instantiated."""
    sys.argv = ["instrumentserver", "--gui", "False", "-c", config_file]
    with (
        patch("instrumentserver.apps.serverWithGui") as mock_gui,
        patch("instrumentserver.apps.server") as mock_srv,
        patch("instrumentserver.apps.PollingWorker") as mock_pw,
        patch("instrumentserver.apps.QtCore.QThread") as mock_qt,
    ):
        from instrumentserver.apps import serverScript

        serverScript()

    mock_srv.assert_called_once()
    mock_gui.assert_not_called()
    mock_pw.assert_called_once_with(pollingRates={"dummy/param": 1.0})
    mock_qt.assert_called_once()

    kwargs = mock_srv.call_args.kwargs
    assert kwargs["pollingThread"] is not None
    assert "shortcutConfig" not in kwargs
    assert "configPath" not in kwargs


@pytest.mark.parametrize("gui", [True, False])
def test_server_script_passthrough_args(gui):
    """Pass-through: --port, --allow_user_shutdown, --listen_at, --init_script arrive unchanged."""
    argv = [
        "instrumentserver",
        "--port",
        "9999",
        "--allow_user_shutdown",
        "True",
        "--listen_at",
        "192.168.1.1",
        "--init_script",
        "/tmp/init.py",
    ]
    if not gui:
        argv += ["--gui", "False"]
    sys.argv = argv

    with (
        patch("instrumentserver.apps.serverWithGui") as mock_gui,
        patch("instrumentserver.apps.server") as mock_srv,
        patch("instrumentserver.apps.loadConfig"),
    ):
        from instrumentserver.apps import serverScript

        serverScript()

    mock_fn = mock_gui if gui else mock_srv
    mock_fn.assert_called_once()
    kwargs = mock_fn.call_args.kwargs
    assert kwargs["port"] == "9999"
    assert kwargs["addresses"] == ["192.168.1.1"]
    assert kwargs["initScript"] == "/tmp/init.py"
    # allowUserShutdown is only forwarded on the headless path
    if not gui:
        assert kwargs["allowUserShutdown"] == "True"


# ---------------------------------------------------------------------------
# Phase 2 — clientStationScript and detachedServerScript unit tests
# ---------------------------------------------------------------------------


def test_client_station_script_no_config():
    """clientStationScript: no -c → ClientStation called with config_path=None."""
    sys.argv = ["instrumentserver-client-station"]
    with (
        patch("instrumentserver.apps.QtWidgets.QApplication") as mock_app,
        patch("instrumentserver.apps.ClientStation") as mock_cs,
        patch("instrumentserver.apps.ClientStationGui"),
    ):
        mock_app.return_value.exec_.return_value = 0
        from instrumentserver.apps import clientStationScript

        clientStationScript()

    mock_cs.assert_called_once_with(host="localhost", port=5555, config_path=None)


def test_client_station_script_with_config(tmp_path):
    """clientStationScript: -c path → ClientStation called with that config_path."""
    cfg = str(tmp_path / "cs.yml")
    sys.argv = ["instrumentserver-client-station", "-c", cfg]
    with (
        patch("instrumentserver.apps.QtWidgets.QApplication") as mock_app,
        patch("instrumentserver.apps.ClientStation") as mock_cs,
        patch("instrumentserver.apps.ClientStationGui"),
    ):
        mock_app.return_value.exec_.return_value = 0
        from instrumentserver.apps import clientStationScript

        clientStationScript()

    mock_cs.assert_called_once_with(host="localhost", port=5555, config_path=cfg)


def test_detached_server_script_defaults():
    """detachedServerScript: defaults → DetachedServerGui called with host=localhost, port=5555."""
    sys.argv = ["instrumentserver-detached"]
    with (
        patch("instrumentserver.apps.QtWidgets.QApplication") as mock_app,
        patch("instrumentserver.apps.DetachedServerGui") as mock_dsg,
    ):
        mock_app.return_value.exec_.return_value = 0
        mock_dsg.return_value.show = MagicMock()
        from instrumentserver.apps import detachedServerScript

        detachedServerScript()

    mock_dsg.assert_called_once_with(host="localhost", port=5555)


def test_detached_server_script_custom():
    """detachedServerScript: custom args → DetachedServerGui called with those values."""
    sys.argv = ["instrumentserver-detached", "--host", "10.0.0.1", "--port", "9000"]
    with (
        patch("instrumentserver.apps.QtWidgets.QApplication") as mock_app,
        patch("instrumentserver.apps.DetachedServerGui") as mock_dsg,
    ):
        mock_app.return_value.exec_.return_value = 0
        mock_dsg.return_value.show = MagicMock()
        from instrumentserver.apps import detachedServerScript

        detachedServerScript()

    mock_dsg.assert_called_once_with(
        host="10.0.0.1", port="9000"
    )  # string because no type= in argparse


# ---------------------------------------------------------------------------
# Phase 3 — parameterManagerScript unit tests
# ---------------------------------------------------------------------------


def test_param_manager_script_instrument_exists():
    """parameterManagerScript: instrument exists → get_instrument path taken."""
    sys.argv = ["instrumentserver-param-manager", "--port", "5555"]
    mock_pm = MagicMock()
    mock_cli = MagicMock()
    mock_cli.list_instruments.return_value = ["parameter_manager"]
    mock_cli.get_instrument.return_value = mock_pm

    with (
        patch("instrumentserver.apps.QtWidgets.QApplication") as mock_app,
        patch("instrumentserver.apps.Client", return_value=mock_cli),
        patch("instrumentserver.apps.widgetMainWindow") as mock_wmw,
        patch("instrumentserver.apps.ParameterManagerGui") as mock_pmg,
    ):
        mock_app.return_value.exec_.return_value = 0
        from instrumentserver.apps import parameterManagerScript

        parameterManagerScript()

    mock_cli.get_instrument.assert_called_once_with("parameter_manager")
    mock_cli.find_or_create_instrument.assert_not_called()
    mock_pmg.assert_called_once_with(mock_pm)
    mock_wmw.assert_called_once()


def test_param_manager_script_instrument_missing():
    """parameterManagerScript: instrument not found → find_or_create path taken."""
    sys.argv = ["instrumentserver-param-manager", "--port", "5555"]
    mock_pm = MagicMock()
    mock_cli = MagicMock()
    mock_cli.list_instruments.return_value = []
    mock_cli.find_or_create_instrument.return_value = mock_pm

    with (
        patch("instrumentserver.apps.QtWidgets.QApplication") as mock_app,
        patch("instrumentserver.apps.Client", return_value=mock_cli),
        patch("instrumentserver.apps.widgetMainWindow") as mock_wmw,
        patch("instrumentserver.apps.ParameterManagerGui") as mock_pmg,
    ):
        mock_app.return_value.exec_.return_value = 0
        from instrumentserver.apps import parameterManagerScript

        parameterManagerScript()

    mock_cli.find_or_create_instrument.assert_called_once_with(
        "parameter_manager", "instrumentserver.params.ParameterManager"
    )
    mock_cli.get_instrument.assert_not_called()
    mock_pm.fromFile.assert_called_once()
    mock_pm.update.assert_called_once()
    mock_pmg.assert_called_once_with(mock_pm)
    mock_wmw.assert_called_once()


# ---------------------------------------------------------------------------
# Phase 4 — Subprocess integration tests
# ---------------------------------------------------------------------------


@pytest.fixture()
def free_port():
    import socket

    with socket.socket() as s:
        s.bind(("", 0))
        port = s.getsockname()[1]
    yield port


@pytest.fixture()
def launch_process(free_port):
    procs = []

    def _launch(args, env_extra=None):
        env = os.environ.copy()
        env["QT_QPA_PLATFORM"] = "offscreen"
        if env_extra:
            env.update(env_extra)
        proc = subprocess.Popen(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
        )
        procs.append(proc)
        return proc

    yield _launch

    for proc in procs:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()


@pytest.mark.integration
def test_subprocess_headless_no_config(free_port, launch_process):
    """instrumentserver --gui False --port <free> starts without crashing."""
    proc = launch_process(
        ["instrumentserver", "--gui", "False", "--port", str(free_port)]
    )
    # Wait for "Starting server." in stderr within 5 seconds
    import select
    import time

    deadline = time.monotonic() + 5
    found = False
    while time.monotonic() < deadline:
        remaining = deadline - time.monotonic()
        r, _, _ = select.select([proc.stderr], [], [], min(remaining, 0.1))
        if r:
            line = proc.stderr.readline().decode(errors="replace")
            if "Starting server." in line:
                found = True
                break
        if proc.poll() is not None:
            break
    assert found, "Server did not emit 'Starting server.' within 5 seconds"


@pytest.mark.integration
def test_subprocess_gui_default(free_port, launch_process):
    """instrumentserver --port <free> (GUI) stays alive for at least 2 seconds."""
    import time

    proc = launch_process(["instrumentserver", "--port", str(free_port)])
    time.sleep(2)
    if proc.poll() is not None:
        stderr_out = proc.stderr.read().decode(errors="replace")
        pytest.fail(
            f"Process exited early (code {proc.returncode}).\nstderr:\n{stderr_out}"
        )


@pytest.mark.integration
def test_subprocess_headless_with_config(free_port, launch_process, tmp_path):
    """instrumentserver --gui False -c config.yml --port <free> starts correctly."""
    cfg = tmp_path / "config.yml"
    cfg.write_text(MINIMAL_CONFIG)

    proc = launch_process(
        [
            "instrumentserver",
            "--gui",
            "False",
            "-c",
            str(cfg),
            "--port",
            str(free_port),
        ]
    )

    import select
    import time

    deadline = time.monotonic() + 5
    found = False
    while time.monotonic() < deadline:
        remaining = deadline - time.monotonic()
        r, _, _ = select.select([proc.stderr], [], [], min(remaining, 0.1))
        if r:
            line = proc.stderr.readline().decode(errors="replace")
            if "Starting server." in line:
                found = True
                break
        if proc.poll() is not None:
            break
    assert found, "Server did not emit 'Starting server.' within 5 seconds"


@pytest.mark.integration
def test_subprocess_detached_server(free_port, launch_process):
    """instrumentserver-detached --port <free> stays alive for at least 2 seconds."""
    import time

    proc = launch_process(["instrumentserver-detached", "--port", str(free_port)])
    time.sleep(2)
    assert proc.poll() is None, f"Process exited early: {proc.returncode}"
