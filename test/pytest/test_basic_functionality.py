import time

from qcodes.math_utils.field_vector import FieldVector


def test_creating_and_accessing_param(param_manager):
    cli, params = param_manager
    params.add_parameter(name="my_param", initial_value=123, unit="M")
    assert params.my_param() == 123
    assert params.my_param.unit == "M"

    params.my_param(456)
    assert params.my_param() == 456


def test_getting_all_instruments(cli):
    cli.find_or_create_instrument(
        "dummy",
        "instrumentserver.testing.dummy_instruments.generic.DummyInstrumentWithSubmodule",
    )
    cli.find_or_create_instrument(
        "parameter_manager", "instrumentserver.params.ParameterManager"
    )
    all_ins = cli.list_instruments()
    expected_dict = ["dummy", "parameter_manager"]
    assert sorted(all_ins) == sorted(expected_dict)


def test_calling_instrument_method(dummy_instrument):
    cli, ins = dummy_instrument
    ins.param0(1)
    assert ins.param0() == 1
    ret = ins.test_func(1, 2, 3, 4, c=[5, 6], d=False, more="hello")

    expected = [1, 2, 3, [5, 6], False, ins.param0()]
    assert expected == ret


def test_closing_instruments(dummy_instrument):
    cli, dummy = dummy_instrument
    assert "dummy" in cli.list_instruments()
    cli.close_instrument(dummy.name)
    assert "dummy" not in cli.list_instruments()


def test_sending_and_receiving_arbitrary_objects(cli, start_server):
    magnet = cli.find_or_create_instrument(
        name="magnet",
        instrument_class="instrumentserver.testing.dummy_instruments.generic.FieldVectorIns",
    )

    # Testing receiving arbitrary return from method
    field_vector = magnet.get_field()
    expected_field = FieldVector(1, 1, 1)
    assert isinstance(field_vector, FieldVector)
    assert field_vector.is_equal(expected_field)

    # Getting the parameter directly instead of through a function
    field_vector = magnet.field()
    assert isinstance(field_vector, FieldVector)
    assert field_vector.is_equal(expected_field)

    # Setting parameter directly.
    new_field_vector = FieldVector(11, 22, 33)
    magnet.field(new_field_vector)
    server_vector = start_server.station.components["magnet"].field_vector
    returned_vector = magnet.field()
    assert isinstance(returned_vector, FieldVector)
    assert server_vector is not new_field_vector
    assert returned_vector is not server_vector
    assert returned_vector.is_equal(new_field_vector)

    new_field_vector = FieldVector(101, 102, 103)
    magnet.set_field(new_field_vector)
    assert magnet.get_field().is_equal(new_field_vector)


def test_the_server_goes_idle_after_answering_requests(cli, start_server):
    """Regression: the Server's request loop is woken when a worker has
    finished a request, and must drain that wakeup. Left undrained, every
    poll returns at once and an idle Server spins a whole core. After a
    few requests the process may use only a fraction of an idle second's
    CPU time; the Server runs in this process, on its own thread."""
    for _ in range(3):
        cli.list_instruments()
    time.sleep(0.5)  # the last response goes out and the loop settles

    start = time.process_time()
    time.sleep(1.0)
    used = time.process_time() - start

    assert used < 0.5, (
        f"the process used {used:.2f} s of CPU time in an idle second: "
        "the Server's request loop does not go idle"
    )
