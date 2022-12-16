

def test_creating_and_accessing_param(param_manager):
    cli, params = param_manager
    params.add_parameter('my_param', initial_value=123, unit='M')
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

