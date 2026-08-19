"""Verification script for docs/getting_started/quickstart.md.

One section below per page section, in page order (see
test/docs_verification/README.md for conventions). Asserts every behavioral
claim the quickstart makes; exits 0 on success.

GUI claims (the server window opening, the live parameter update, the
double-click-to-open generic instrument window and editing parameters from
it, the Parameter Manager widget embedded in the server window) cannot be
asserted here; they are verified manually and captured in the page's
screenshots.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from helpers import capture_broadcasts, client, server, server_process

GENERATOR_CLASS = "instrumentserver.testing.dummy_instruments.rf.Generator"
CONFIG = str(Path(__file__).parent / "quickstartConfig.yml")


# ---------------------------------------------------------------------------
# Section: Start the server (bare, no config file)
#
# Page claim: running plain `instrumentserver` starts a Server with no
# instruments, ready to take client connections. (The page shows the GUI
# variant; the CLI subprocess here is the same launcher, headless.)
# ---------------------------------------------------------------------------
def section_start_bare() -> None:
    with server_process():
        with client() as cli:
            # NOTE: list_instruments() is annotated Dict[str, str] but the
            # server actually answers with a list of names (audit entry).
            instruments = cli.list_instruments()
            assert instruments == [], (
                f"A bare server should start with no instruments, got {instruments!r}"
            )
    print("section_start_bare: OK")


# ---------------------------------------------------------------------------
# Section: First client connection; create a Dummy Instrument
#
# Page claims: a Client connects to a running server on the default port;
# find_or_create_instrument creates the dummy RF generator on the Server and
# returns a Proxy Instrument; the generator comes up with its documented
# initial values; calling find_or_create_instrument again finds the existing
# instrument instead of failing.
# ---------------------------------------------------------------------------
def section_first_client() -> None:
    with server():
        with client() as cli:
            generator = cli.find_or_create_instrument("generator", GENERATOR_CLASS)

            assert "generator" in cli.list_instruments()

            # The Proxy Instrument mirrors the real instrument's interface;
            # the page shows this exact parameter list.
            assert sorted(generator.parameters) == [
                "IDN",
                "frequency",
                "power",
                "rf_on",
            ], sorted(generator.parameters)

            assert generator.frequency() == 10e9
            assert generator.power() == -100
            assert generator.rf_on() is False

            # Second call: finds, does not re-create or fail.
            again = cli.find_or_create_instrument("generator", GENERATOR_CLASS)
            assert again.frequency() == 10e9
    print("section_first_client: OK")


# ---------------------------------------------------------------------------
# Section: Get and set a parameter; the Server broadcasts the change
#
# Page claims: parameters are read by calling them and set by calling them
# with a value; every change on the Server goes out as a Broadcast (which is
# why the GUI follows along live without refreshing).
# ---------------------------------------------------------------------------
def section_get_set_broadcast() -> None:
    with server():
        with client() as cli:
            generator = cli.find_or_create_instrument("generator", GENERATOR_CLASS)

            with capture_broadcasts() as cap:
                generator.frequency(5e9)
                messages = cap.wait_for(1)

            assert generator.frequency() == 5e9
            text = repr(messages)
            assert "frequency" in text, (
                f"Expected a Broadcast about 'frequency', got: {text}"
            )
    print("section_get_set_broadcast: OK")


# ---------------------------------------------------------------------------
# Section: Starting with a config file
#
# Page claims: the same setup can be declared in YAML; an instrument marked
# initialize: True exists as soon as the server is up, no client call needed.
# Uses the exact config file the page shows (quickstartConfig.yml).
# ---------------------------------------------------------------------------
def section_config_file() -> None:
    with server_process(config=CONFIG):
        with client() as cli:
            instruments = cli.list_instruments()
            assert "generator" in instruments, instruments

            # The declared generator is the same instrument the page created
            # programmatically earlier.
            generator = cli.get_instrument("generator")
            assert generator.frequency() == 10e9
    print("section_config_file: OK")


# ---------------------------------------------------------------------------
# Section: Where to go next — links only, nothing to verify.
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    section_start_bare()
    section_first_client()
    section_get_set_broadcast()
    section_config_file()
    print("verify_quickstart: all sections OK")
