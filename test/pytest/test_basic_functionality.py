from qcodes.math_utils.field_vector import FieldVector


def test_creating_and_accessing_param(param_manager):
    cli, params = param_manager
    params.add_parameter(name='my_param', initial_value=123, unit='M')
    assert params.my_param() == 123
    assert params.my_param.unit == 'M'

    params.my_param(456)
    assert params.my_param() == 456


def test_getting_all_instruments(cli):
    dummy = cli.find_or_create_instrument('dummy',
                                          'instrumentserver.testing.dummy_instruments.generic.DummyInstrumentWithSubmodule')
    params = cli.find_or_create_instrument('parameter_manager', 'instrumentserver.params.ParameterManager')
    all_ins = cli.list_instruments()
    expected_dict = ['dummy', 'parameter_manager']
    assert sorted(all_ins) == sorted(expected_dict)


def test_calling_instrument_method(dummy_instrument):
    cli, ins = dummy_instrument
    ins.param0(1)
    assert ins.param0() == 1
    ret = ins.test_func(1, 2, 3, 4, c=[5, 6], d=False, more='hello')

    expected = [1, 2, 3, [5, 6], False, ins.param0()]
    assert expected == ret


def test_closing_instruments(dummy_instrument):
    cli, dummy = dummy_instrument
    assert 'dummy' in cli.list_instruments()
    cli.close_instrument(dummy.name)
    assert 'dummy' not in cli.list_instruments()


def test_sending_and_receiving_arbitrary_objects(cli):
    magnet = cli.find_or_create_instrument(name='magnet', instrument_class='instrumentserver.testing.dummy_instruments.generic.FieldVectorIns')

    # Testing receiving arbitrary return from method
    field_vector = magnet.get_field()
    expected_field = FieldVector(1, 1, 1)
    assert field_vector.is_equal(expected_field)

    # Getting the parameter directly instead of through a function
    field_vector = magnet.field()
    assert field_vector.is_equal(expected_field)

    # Setting parameter directly.
    new_field_vector = FieldVector(11, 22, 33)
    magnet.field(new_field_vector)
    assert magnet.field().is_equal(new_field_vector)

    new_field_vector = FieldVector(101, 102, 103)
    magnet.set_field(new_field_vector)
    assert magnet.get_field().is_equal(new_field_vector)

