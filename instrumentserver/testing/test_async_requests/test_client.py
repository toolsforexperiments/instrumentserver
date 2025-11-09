from instrumentserver.client import Client


'''
A simple test script for the concurrence feature on the server.

With the server started, run the full code below in one console,
then comment out the `dummy1.get_random_timeout` line, run the code in a new console, the `dummy2.get_random` should
be able to return immediately.
Without concurrence on the server, the `dummy2.get_random` in the new console won't return until the dummy1 in the first
console is done.


This mimics the case when on client is ramping bias voltage, while another client wants to change a parameter of
a different instrument. Or more commonly, a client is ramping bias voltage, and we want to view parameter of an instrument
in the server gui (which also is basically another client that runs in a different console.)
'''

if __name__ == "__main__":
    cli = Client(timeout=50, port=5555)
    import time
    t0 = time.time()
    dummy1 = cli.find_or_create_instrument('test1',
                                           'instrumentserver.testing.dummy_instruments.generic.DummyInstrumentTimeout')
    dummy2 = cli.find_or_create_instrument('test2',
                                           'instrumentserver.testing.dummy_instruments.generic.DummyInstrumentTimeout')
    
    # print(dummy1.get_random_timeout(10))
    print(dummy1.get_random())
    print(dummy2.get_random())
    
    
    # for i in range(20):
    #     print(dummy1.get_random())
    #     print(dummy2.get_random())
    
    print(f"took {time.time() - t0} seconds")


