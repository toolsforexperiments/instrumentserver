import instrumentserver.testing.dummy_instruments.generic
import pytest  # type: ignore[import-not-found]

from instrumentserver.server.core import startServer
from instrumentserver.client.core import BaseClient
from instrumentserver.client.proxy import Client


@pytest.fixture(scope='session')
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


@pytest.fixture(scope='module')
def start_server(qapp_session):
    server, thread = startServer()
    yield server
    # The zmq loop in StationServer blocks on poll(); thread.quit() on its own
    # won't interrupt it. Send the SAFEWORD so the server shuts itself down,
    # then wait for the thread's event loop to exit.
    try:
        with BaseClient() as shutdown_cli:
            shutdown_cli.ask(server.SAFEWORD)
    except Exception:
        pass
    thread.wait(5000)
    thread.deleteLater()


@pytest.fixture()
def cli(start_server):
    cli = Client()
    yield cli
    cli.disconnect()


@pytest.fixture()
def dummy_instrument(cli):
    dummy = cli.find_or_create_instrument('dummy', 'instrumentserver.testing.dummy_instruments.generic.DummyInstrumentWithSubmodule')
    return cli, dummy


@pytest.fixture()
def param_manager(cli):
    params = cli.find_or_create_instrument('parameter_manager', 'instrumentserver.params.ParameterManager')
    return cli, params



