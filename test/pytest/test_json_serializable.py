import instrumentserver.testing.dummy_instruments.generic
import qcodes as qc
from qcodes.math_utils.field_vector import FieldVector

from instrumentserver.blueprints import (bluePrintFromInstrumentModule,
                                         bluePrintFromMethod,
                                         bluePrintFromParameter,
                                         bluePrintToDict,
                                         deserialize_obj,
                                         ParameterBroadcastBluePrint,
                                         iterable_to_serialized_dict,
                                         dict_to_serialized_dict,
                                         )
from instrumentserver.testing.dummy_instruments.generic import DummyInstrumentWithSubmodule
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

    attributes = ['x', 'y', 'z']

    def __init__(self, x=1, y=2, z=3):
        self.x = x
        self.y = y
        self.z = z


    def customFunction(self, x: int, y:int) -> int:
        print(f'I am in my function')
        return x*y


def test_basic_param_dictionary():
    my_param = CustomParameter(name='my_param', unit='M')
    param_bp = bluePrintFromParameter('', my_param)
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
    my_rr = ResonatorResponse('rr')
    instrument_bp = bluePrintFromInstrumentModule("", my_rr)
    bp_dict = bluePrintToDict(instrument_bp)
    reconstructed_bp = deserialize_obj(bp_dict)
    assert instrument_bp == reconstructed_bp

    my_dummy = DummyInstrumentWithSubmodule('dummy')
    dummy_bp = bluePrintFromInstrumentModule("", my_dummy)
    dummy_bp_dict = bluePrintToDict(dummy_bp)
    reconstructed_dummy_bp = deserialize_obj(dummy_bp_dict)
    assert dummy_bp == reconstructed_dummy_bp


def test_basic_broadcast_parameter_dictionary():
    broadcast_bp = ParameterBroadcastBluePrint(name='my_param', action='an_action', value=-56, unit='M')
    bp_dict = bluePrintToDict(broadcast_bp)
    reconstructed_bp = deserialize_obj(bp_dict)
    assert broadcast_bp == reconstructed_bp


def test_arbitrary_class_serialization():
    arbitrary_class_1 = MyClass()
    arbitrary_class_2 = MyClass(x=10, y=11, z=12)

    expected_arg = [{'x': 1, 'y': 2, 'z': 3,
                     '_class_type': {'module': arbitrary_class_1.__module__,
                                     'type': arbitrary_class_1.__class__.__name__}}]
    expected_kwargs = {'arbitrary_class_2': {'x': 10, 'y': 11, 'z': 12,
                                             '_class_type': {'module': arbitrary_class_2.__module__,
                                                             'type': arbitrary_class_2.__class__.__name__}}}

    returned_args = iterable_to_serialized_dict([arbitrary_class_1])
    returned_kwargs = dict_to_serialized_dict({'arbitrary_class_2': arbitrary_class_2})
    assert returned_args == expected_arg
    assert expected_kwargs == returned_kwargs


def test_send_arbitrary_objects(cli):

    field_vector_ins = cli.find_or_create_instrument('field_vector', instrument_class="instrumentserver.testing.dummy_instruments.generic.FieldVectorIns")

    new_vector = FieldVector(x=12.0, y=12.0, z=12.0)
    field_vector_ins.set_field(new_vector)

    ins_vector = field_vector_ins.get_field()
    assert new_vector.is_equal(ins_vector)


def test_sending_complex_numbers(cli):
    field_vector_ins = cli.find_or_create_instrument('field_vector',
                                                     instrument_class="instrumentserver.testing.dummy_instruments.generic.FieldVectorIns")

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
