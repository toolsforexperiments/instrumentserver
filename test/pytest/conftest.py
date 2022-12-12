import instrumentserver.testing.dummy_instruments.generic
import pytest

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
def server_client(start_server):
    cli = Client()
    return cli

@pytest.fixture()
def dummy_instrument(server_client):
    dummy = server_client.find_or_create_instrument('dummy', 'instrumentserver.testing.dummy_instruments.generic.DummyInstrumentWithSubmodule')
    return server_client, dummy





