from instrumentserver.client import Client


'''
A simple script for testing the new features on the server/client.

'''

if __name__ == "__main__":
    cli = Client(timeout=15000, port=5555)
    import time
    t0 = time.time()
    dummy1 = cli.find_or_create_instrument('test1',
                                           'instrumentserver.testing.dummy_instruments.generic.DummyInstrumentTimeout')
    dummy2 = cli.find_or_create_instrument('test2',
                                           'instrumentserver.testing.dummy_instruments.generic.DummyInstrumentTimeout')
    
    # print(dummy1.get_random_timeout(10))
    print(dummy2.get_random())
    dummy1.param2(1e9)
    
    # for i in range(20):
    #     print(dummy1.get_random())
    #     print(dummy2.get_random())
    
    print(f"took {time.time() - t0} seconds")


