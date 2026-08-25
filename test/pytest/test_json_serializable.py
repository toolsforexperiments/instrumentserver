import json

import numpy as np
import pytest
import qcodes as qc
from qcodes.math_utils.field_vector import FieldVector

from instrumentserver.base import decode, encode
from instrumentserver.blueprints import (
    CallSpec,
    Operation,
    ParameterBroadcastBluePrint,
    ServerInstruction,
    ServerResponse,
    bluePrintFromInstrumentModule,
    bluePrintFromMethod,
    bluePrintFromParameter,
    bluePrintToDict,
    deserialize_obj,
    dict_to_serialized_dict,
    iterable_to_serialized_dict,
)
from instrumentserver.testing.dummy_instruments.generic import (
    DummyInstrumentTimeout,
    DummyInstrumentWithSubmodule,
    FieldVectorIns,
    SweepRequest,
    SweepResult,
)
from instrumentserver.testing.dummy_instruments.rf import ResonatorResponse


class CustomParameter(qc.Parameter):
    def __int__(self, name, *args, **kwargs):
        """
        Well lets see if you go anywhere
        """
        super().__init__(name, *args, **kwargs)
        self.value = 0

    def get_raw(self):
        return self.value

    def set_raw(self, val):
        self.value = val
        return self.value


class MyClass:
    attributes = ["x", "y", "z"]

    def __init__(self, x=1, y=2, z=3):
        self.x = x
        self.y = y
        self.z = z

    def customFunction(self, x: int, y: int) -> int:
        print("I am in my function")
        return x * y


class NestedPayload:
    attributes = ("request",)

    def __init__(self, request):
        self.request = request


class ArrayPayload:
    attributes = ("values",)

    def __init__(self, values):
        self.values = values


class ConstructorRejectsFields:
    def __init__(self):
        pass


def test_basic_param_dictionary():
    my_param = CustomParameter(name="my_param", unit="M")
    param_bp = bluePrintFromParameter("", my_param)
    bp_dict = bluePrintToDict(param_bp)
    reconstructed_bp = deserialize_obj(bp_dict)
    assert param_bp == reconstructed_bp


def test_basic_function_dictionary():
    my_method = MyClass.customFunction
    method_bp = bluePrintFromMethod("", my_method)
    bp_dict = bluePrintToDict(method_bp)
    reconstructed_bp = deserialize_obj(bp_dict)
    assert method_bp == reconstructed_bp


def test_basic_instrument_dictionary():
    my_rr = ResonatorResponse("rr")
    instrument_bp = bluePrintFromInstrumentModule("", my_rr)
    bp_dict = bluePrintToDict(instrument_bp)
    reconstructed_bp = deserialize_obj(bp_dict)
    assert instrument_bp == reconstructed_bp

    my_dummy = DummyInstrumentWithSubmodule("dummy")
    dummy_bp = bluePrintFromInstrumentModule("", my_dummy)
    dummy_bp_dict = bluePrintToDict(dummy_bp)
    reconstructed_dummy_bp = deserialize_obj(dummy_bp_dict)
    assert dummy_bp == reconstructed_dummy_bp


def test_timeout_dummy_responds_to_idn():
    instrument = DummyInstrumentTimeout("timeout_dummy")
    try:
        assert instrument.get_idn() == {
            "vendor": "dummy",
            "model": "timeout_dummy",
            "serial": "0",
            "firmware": "0",
        }
    finally:
        instrument.close()


def test_field_vector_dummy_responds_to_idn_without_error_log(caplog):
    instrument = FieldVectorIns("field_vector_idn")
    try:
        assert instrument.get_idn() == {
            "vendor": "dummy",
            "model": "field_vector_idn",
            "serial": "0",
            "firmware": "0",
        }
        assert "NotImplementedError" not in caplog.text
    finally:
        instrument.close()


def test_custom_dataclass_request_and_result_codec():
    request = SweepRequest(5e9, 20e6, {"sample": "A"})
    instruction = ServerInstruction(
        operation=Operation.call,
        call_spec=CallSpec(target="analyzer.run_sweep", args=(request,)),
    )
    decoded_instruction = decode(encode(instruction))
    decoded_request = decoded_instruction.call_spec.args[0]
    assert isinstance(decoded_request, SweepRequest)
    assert decoded_request == request
    assert decoded_request is not request

    result = SweepResult([4.99e9, 5e9, 5.01e9], [-50.0, -20.0, -49.0])
    decoded_response = decode(encode(ServerResponse(message=result)))
    assert isinstance(decoded_response.message, SweepResult)
    assert decoded_response.message == result
    assert decoded_response.message is not result


def test_custom_serialization_requirements_and_non_recursive_fields():
    request = SweepRequest(5e9, 20e6)
    nested = ServerInstruction(
        operation=Operation.call,
        call_spec=CallSpec(target="echo", args=(NestedPayload(request),)),
    )
    with pytest.raises(TypeError, match="SweepRequest"):
        encode(nested)

    array = ServerInstruction(
        operation=Operation.call,
        call_spec=CallSpec(target="echo", args=(ArrayPayload(np.array([1])),)),
    )
    with pytest.raises(TypeError, match="ndarray"):
        encode(array)

    with pytest.raises(ModuleNotFoundError):
        decode(
            json.dumps(
                {
                    "value": 1,
                    "_class_type": "missing_package.models.Value",
                }
            )
        )

    constructor_path = (
        f"{ConstructorRejectsFields.__module__}.{ConstructorRejectsFields.__name__}"
    )
    with pytest.raises(TypeError, match="unexpected keyword argument"):
        decode(json.dumps({"value": 1, "_class_type": constructor_path}))


@pytest.mark.parametrize(
    ("encoded", "expected"),
    [
        ("123", 123),
        ("1.5", 1.5),
        ("True", True),
        ("plain text", "plain text"),
    ],
)
def test_scalar_text_coercion(encoded, expected):
    assert deserialize_obj(encoded) == expected


def test_basic_broadcast_parameter_dictionary():
    broadcast_bp = ParameterBroadcastBluePrint(
        name="my_param", action="an_action", value=-56, unit="M"
    )
    bp_dict = bluePrintToDict(broadcast_bp)
    reconstructed_bp = deserialize_obj(bp_dict)
    assert broadcast_bp == reconstructed_bp


def test_arbitrary_class_serialization():
    arbitrary_class_1 = MyClass()
    arbitrary_class_2 = MyClass(x=10, y=11, z=12)

    expected_arg = [
        {
            "x": 1,
            "y": 2,
            "z": 3,
            "_class_type": f"{arbitrary_class_1.__module__}.{arbitrary_class_1.__class__.__name__}",
        }
    ]
    expected_kwargs = {
        "arbitrary_class_2": {
            "x": 10,
            "y": 11,
            "z": 12,
            "_class_type": f"{arbitrary_class_2.__module__}.{arbitrary_class_2.__class__.__name__}",
        }
    }

    returned_args = iterable_to_serialized_dict([arbitrary_class_1])
    returned_kwargs = dict_to_serialized_dict({"arbitrary_class_2": arbitrary_class_2})
    assert returned_args == expected_arg
    assert expected_kwargs == returned_kwargs


def test_send_arbitrary_objects(cli):

    field_vector_ins = cli.find_or_create_instrument(
        "field_vector",
        instrument_class="instrumentserver.testing.dummy_instruments.generic.FieldVectorIns",
    )

    new_vector = FieldVector(x=12.0, y=12.0, z=12.0)
    field_vector_ins.set_field(new_vector)

    ins_vector = field_vector_ins.get_field()
    assert new_vector.is_equal(ins_vector)


def test_sending_complex_numbers(cli):
    field_vector_ins = cli.find_or_create_instrument(
        "field_vector",
        instrument_class="instrumentserver.testing.dummy_instruments.generic.FieldVectorIns",
    )

    # Getting value
    expected_complex = 1 + 1j
    ret_complex = field_vector_ins.complex()
    assert expected_complex == ret_complex

    # Setting value
    new_complex = 2 - 4j
    field_vector_ins.complex(new_complex)
    assert new_complex == field_vector_ins.complex()

    # Getting lists
    expected_list = [1 + 1j, -2 - 2j]
    ret_list = field_vector_ins.complex_list()
    assert expected_list == ret_list
    ret_list = field_vector_ins.get_complex_list()
    assert expected_list == ret_list

    # Setting lists
    new_list = [3 + 3j, -4 - 4j]
    field_vector_ins.complex_list(new_list)
    assert new_list == field_vector_ins.complex_list()

    new_list = [5 + 5j, -6 - 6j]
    field_vector_ins.set_complex_list(new_list)
    assert new_list == field_vector_ins.get_complex_list()

    new_list = [5 + 5j, -6, -6j]
    field_vector_ins.set_complex_list(new_list)
    assert new_list == field_vector_ins.get_complex_list()

    numpy_array = np.array([1, 2, 3, 4, 5, 4 - 1j])
    field_vector_ins.set_complex_list(numpy_array)
    ret_numpy_array = field_vector_ins.complex_list()
    assert isinstance(ret_numpy_array, np.ndarray)
    assert np.array_equal(numpy_array, field_vector_ins.complex_list())
