

def test_creating_and_accessing_param(param_manager):
    cli, params = param_manager
    params.add_parameter('my_param', initial_value=123, unit='M')
    assert params.my_param() == 123
    assert params.my_param.unit == 'M'

    params.my_param(456)
    assert params.my_param() == 456


def test_calling_instrument_method(dummy_instrument):
    cli, ins = dummy_instrument

    ins.param0(1)
    assert ins.param0() == 1

    ret = ins.test_func(1, 2, 3, c=[4, 5, 6], d=True)
    assert (1, 2, 3, [4, 5, 6], True, 1) == ret

