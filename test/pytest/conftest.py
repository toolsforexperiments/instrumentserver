import random
import socket

import pytest  # type: ignore[import-not-found]
import qcodes as qc

from instrumentserver.client.core import BaseClient
from instrumentserver.client.proxy import Client
from instrumentserver.server.core import startServer


@pytest.fixture(scope="session")
def server_port():
    """Pick a free pair of consecutive ports, once per pytest session.

    The Server binds ``port`` for requests and uses ``port + 1`` for
    Broadcasts, so both must be free. Several agents run the suite in
    parallel; fixed ports made those runs collide. The first port is
    drawn randomly from a wide range — deliberately outside the OS
    ephemeral port range, whose sequential allocation hands concurrently
    starting sessions adjacent, overlapping pairs — and both ports are
    then verified to be free.
    """

    def _pair_is_free(port):
        try:
            with socket.socket() as first, socket.socket() as second:
                first.bind(("", port))
                second.bind(("", port + 1))
            return True
        except OSError:
            return False

    for _ in range(100):
        port = random.randrange(20_000, 40_000)
        if _pair_is_free(port):
            return port
    raise RuntimeError("Could not find two free consecutive ports.")


@pytest.fixture(autouse=True, scope="module")
def _close_instruments_between_modules():
    """Ensure every test module starts with a clean qcodes instrument registry.

    qcodes.Instrument._all_instruments is a class-level weakref dict that
    persists for the entire pytest session. Instruments left behind by one
    module (e.g. channel submodules, which qcodes.Instrument.close() does not
    cascade-close in this qcodes version) cause KeyError collisions when the
    next module tries to create an instrument with the same name.
    """
    yield
    qc.Instrument.close_all()


@pytest.fixture(scope="session")
def qapp_session():
    """Ensure a QApplication exists for the entire test session.

    QThread (used by startServer) requires a running QApplication.
    pytest-qt provides 'qapp' per-session, but only when qtbot is requested.
    This fixture guarantees the app exists even for non-GUI tests.
    """
    from instrumentserver import QtWidgets

    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication([])
    return app


@pytest.fixture(scope="module")
def start_server(qapp_session, server_port):
    server, thread = startServer(port=server_port)
    yield server
    # The zmq loop in StationServer blocks on poll(); thread.quit() on its own
    # won't interrupt it. Send the SAFEWORD so the server shuts itself down,
    # then wait for the thread's event loop to exit.
    try:
        with BaseClient(port=server_port) as shutdown_cli:
            shutdown_cli.ask(server.SAFEWORD)
    except Exception:
        pass
    thread.wait(5000)
    thread.deleteLater()


@pytest.fixture()
def cli(start_server, server_port):
    cli = Client(port=server_port)
    yield cli
    cli.disconnect()


@pytest.fixture()
def dummy_instrument(cli):
    dummy = cli.find_or_create_instrument(
        "dummy",
        "instrumentserver.testing.dummy_instruments.generic.DummyInstrumentWithSubmodule",
    )
    return cli, dummy


@pytest.fixture()
def param_manager(cli):
    params = cli.find_or_create_instrument(
        "parameter_manager", "instrumentserver.params.ParameterManager"
    )
    return cli, params
