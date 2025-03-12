import instrumentserver.testing.dummy_instruments.generic
import pytest  # type: ignore[import-not-found]

from instrumentserver.server.core import startServer
from instrumentserver.client.proxy import Client


@pytest.fixture(scope='module')
def start_server():
    server, thread = startServer()
    yield server
    thread.quit()
    thread.deleteLater()
    thread = None


@pytest.fixture()
def cli(start_server):
    cli = Client()
    return cli


@pytest.fixture()
def dummy_instrument(cli):
    dummy = cli.find_or_create_instrument('dummy', 'instrumentserver.testing.dummy_instruments.generic.DummyInstrumentWithSubmodule')
    return cli, dummy


@pytest.fixture()
def param_manager(cli):
    params = cli.find_or_create_instrument('parameter_manager', 'instrumentserver.params.ParameterManager')
    return cli, params



