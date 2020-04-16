from qcodes import Station, Instrument, Parameter
from instrumentserver.serialize import toParamDict


def test_toParamDict_paramsBasic():
    """Test serializing a few parameters added to a station"""

    paramNames = [f"parameter_{i}" for i in range(4)]
    paramValues = [123, None, True, 'abcdef']
    params = []

    for n, v in zip(paramNames, paramValues):
        params.append(Parameter(n, unit="unit", set_cmd=None, initial_value=v))

    station = Station(*params)

    # test simple format
    paramDict_test = toParamDict(station, simpleFormat=True)
    paramDict_expt = {}
    for n, v in zip(paramNames, paramValues):
        paramDict_expt[n] = v

    assert paramDict_test == paramDict_expt

