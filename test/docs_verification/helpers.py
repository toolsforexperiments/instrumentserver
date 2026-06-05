"""Shared helpers for docs verification scripts.

The single canonical way verification scripts start servers, get clients, and
capture Broadcasts (see README.md in this directory). Mirrors the pytest
fixtures in test/pytest/conftest.py wherever one exists; helpers that prove
broadly useful are candidates to graduate into fixtures during the audit
harvest.

Two ways to run a server:

- ``server(...)``: in-process, wrapping ``startServer()`` on a QThread exactly
  like the ``start_server`` pytest fixture. Fast, clean teardown, and the
  yielded ``StationServer`` object can be inspected directly.
- ``server_process(...)``: the real ``instrumentserver`` CLI as a subprocess,
  for sections whose claims are about launch behavior itself.

Both default to port 5555 (the package's ``DEFAULT_PORT``, what every docs
example shows) and fail immediately with a clear message if the port is taken.
"""

import socket
import subprocess
import time
from contextlib import contextmanager
from typing import Any, Iterator, List, Optional, Sequence

import qcodes as qc

from instrumentserver import DEFAULT_PORT, QtCore, QtWidgets
from instrumentserver.client.core import BaseClient
from instrumentserver.client.proxy import Client, SubClient
from instrumentserver.server.core import StationServer, startServer

#: Import path of the standard test instrument, same as the pytest fixtures use.
DUMMY_INSTRUMENT = (
    "instrumentserver.testing.dummy_instruments.generic.DummyInstrumentWithSubmodule"
)


#: Keeps the QApplication alive for the whole script. Without a held
#: reference it gets garbage-collected, destroying every QObject with it.
_qapp: Any = None


def ensure_qapp() -> Any:
    """Make sure a QApplication exists (QThread, used by startServer, needs one)."""
    global _qapp
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication([])
    _qapp = app
    return app


def _require_port_free(port: int) -> None:
    """Fail loudly if ``port`` is already bound (e.g. a leftover server)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("127.0.0.1", port))
        except OSError as e:
            raise RuntimeError(
                f"Port {port} is already in use. Is another instrumentserver "
                f"(or a leftover one) running? Stop it or pass a different port."
            ) from e


@contextmanager
def server(
    config: Optional[str] = None, port: int = DEFAULT_PORT, **kwargs: Any
) -> Iterator[StationServer]:
    """Run an in-process server, shut down cleanly on exit.

    :param config: optional path to a station config YAML, passed to
        ``startServer(stationConfig=...)``.
    :param port: request port; Broadcasts go out on ``port + 1``.
    :param kwargs: forwarded to ``startServer()``.
    """
    _require_port_free(port)
    _require_port_free(port + 1)
    ensure_qapp()
    srv, thread = startServer(port=port, stationConfig=config, **kwargs)
    try:
        yield srv
    finally:
        # The zmq loop in StationServer blocks on poll(); ask it to shut
        # itself down via the SAFEWORD, then wait for the thread to exit.
        # (Same dance as the start_server pytest fixture.)
        try:
            with BaseClient(port=port) as shutdown_cli:
                shutdown_cli.ask(srv.SAFEWORD)
        except Exception:
            pass
        thread.wait(5000)
        thread.deleteLater()
        # Clean the qcodes instrument registry so a script can start more
        # than one server without name collisions.
        qc.Instrument.close_all()


@contextmanager
def server_process(
    config: Optional[str] = None,
    port: int = DEFAULT_PORT,
    extra_args: Sequence[str] = (),
    startup_timeout: float = 15.0,
) -> Iterator["subprocess.Popen[str]"]:
    """Run the real ``instrumentserver`` CLI (headless) as a subprocess.

    Waits until the request port accepts connections before yielding. The
    server's SAFEWORD is randomized per process, so teardown terminates the
    process instead of asking politely.

    :param config: optional config file path, passed as ``-c``.
    :param port: request port, passed as ``-p``.
    :param extra_args: additional CLI arguments, appended verbatim.
    """
    _require_port_free(port)
    _require_port_free(port + 1)
    cmd = ["instrumentserver", "--gui", "False", "-p", str(port)]
    if config is not None:
        cmd += ["-c", config]
    cmd += list(extra_args)
    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
    )
    deadline = time.monotonic() + startup_timeout
    while True:
        if proc.poll() is not None:
            out = proc.stdout.read() if proc.stdout else ""
            raise RuntimeError(
                f"instrumentserver exited during startup "
                f"(code {proc.returncode}). Output:\n{out}"
            )
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                break
        except OSError:
            if time.monotonic() > deadline:
                proc.terminate()
                raise RuntimeError(
                    f"instrumentserver did not open port {port} "
                    f"within {startup_timeout}s"
                )
            time.sleep(0.1)
    try:
        yield proc
    finally:
        proc.terminate()
        try:
            proc.wait(5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(5)


@contextmanager
def client(
    host: str = "localhost", port: int = DEFAULT_PORT, **kwargs: Any
) -> Iterator[Client]:
    """Yield a connected ``Client``, disconnected on exit."""
    cli = Client(host=host, port=port, **kwargs)
    try:
        yield cli
    finally:
        cli.disconnect()


class BroadcastCapture:
    """Collects everything a ``SubClient`` receives. Use via ``capture_broadcasts``."""

    def __init__(self) -> None:
        self.messages: List[Any] = []

    def _collect(self, message: Any) -> None:
        # Runs in the SubClient's thread (DirectConnection); list.append is
        # atomic under the GIL, so no lock is needed.
        self.messages.append(message)

    def wait_for(self, n: int = 1, timeout: float = 5.0) -> List[Any]:
        """Block until at least ``n`` messages arrived; return them all."""
        deadline = time.monotonic() + timeout
        while len(self.messages) < n:
            if time.monotonic() > deadline:
                raise TimeoutError(
                    f"Expected {n} Broadcast(s) within {timeout}s, "
                    f"got {len(self.messages)}: {self.messages!r}"
                )
            time.sleep(0.05)
        return list(self.messages)


@contextmanager
def capture_broadcasts(
    instruments: Optional[List[str]] = None,
    host: str = "localhost",
    port: int = DEFAULT_PORT + 1,
) -> Iterator[BroadcastCapture]:
    """Capture Broadcasts through a ``SubClient`` (the intended live-update path).

    Runs the SubClient on its own QThread, like real consumers do, and yields
    a ``BroadcastCapture`` whose ``messages`` list fills up live.

    :param instruments: instrument names to subscribe to; None means all.
    :param port: the Broadcast port (request port + 1).
    """
    ensure_qapp()
    capture = BroadcastCapture()
    sub = SubClient(instruments=instruments, sub_host=host, sub_port=port)
    sub.update.connect(capture._collect, QtCore.Qt.DirectConnection)
    thread = QtCore.QThread()
    sub.moveToThread(thread)
    thread.started.connect(sub.connect)
    sub.finished.connect(thread.quit)
    thread.start()
    # PUB/SUB slow-joiner: give the SUB socket a moment to connect before the
    # caller triggers the Broadcasts it wants to observe.
    time.sleep(0.3)
    try:
        yield capture
    finally:
        sub.stop()
        thread.wait(2000)
        thread.deleteLater()
