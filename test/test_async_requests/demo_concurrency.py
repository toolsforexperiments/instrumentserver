from instrumentserver.client import Client
import sys
import time

'''
Simple concurrency demo.

Usage (server already running):

Terminal A (long-running call on dummy1):
    python demo_concurrency.py ramp

Terminal B (start while A is still running):

    # Case 1: same instrument -> should block behind ramp
    python demo_concurrency.py same

    # Case 2: different instrument -> should return immediately
    python demo_concurrency.py other



This mimics the case when one client is ramping bias voltage, while another client wants to change a parameter of
a different instrument. Or more commonly, a client is ramping bias voltage, and we want to view parameter of an instrument
in the server gui (which also is basically another client that runs in a different thread.)
'''

if __name__ == "__main__":
    role = sys.argv[1] if len(sys.argv) > 1 else "ramp"
    print(f"[demo] role = {role}")

    cli = Client(timeout=50, port=5555)

    # We only create what we need for the role, but this is cheap anyway
    dummy1 = cli.find_or_create_instrument(
        "test1",
        "instrumentserver.testing.dummy_instruments.generic.DummyInstrumentTimeout",
    )
    dummy2 = cli.find_or_create_instrument(
        "test2",
        "instrumentserver.testing.dummy_instruments.generic.DummyInstrumentTimeout",
    )

    t0 = time.time()

    if role == "ramp": # within a single process, operations are always blocking
        print("[ramp] dummy1.get_random_timeout(10)")
        print(dummy1.get_random_timeout(10))
        print("[after ramp] dummy2.get_random()")
        print(dummy2.get_random())

    elif role == "same": # from a different process, operations on the same instrument are still blocked
        print("[same] dummy1.get_random() (same instrument as ramp)")
        print(dummy1.get_random())

    elif role == "other": # from a different process, operations on a different instrument are NOT blocked
        print("[other] dummy2.get_random() (different instrument)")
        print(dummy2.get_random())

    else:
        print(f"Unknown role {role!r}. Use 'ramp', 'same', or 'other'.")

    print(f"[{role}] took {time.time() - t0:.3f} s")


