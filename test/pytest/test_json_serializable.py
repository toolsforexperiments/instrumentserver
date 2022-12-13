import qcodes as qc

from instrumentserver.blueprints import bluePrintFromInstrumentModule, bluePrintFromMethod, bluePrintFromParameter, bluePrintToDict, bluePrintFromDict


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

    def customFunction(self, x: int, y:int) -> int:
        print(f'I am in my function')
        return x*y


def test_basic_param_dictionary():
    my_param = CustomParameter(name='my_param', unit='M')
    param_bp = bluePrintFromParameter('', my_param)
    bp_dict = bluePrintToDict(param_bp)
    reconstructed_bp = bluePrintFromDict(bp_dict)
    assert param_bp == reconstructed_bp


def test_basic_function_dictionary():
    my_method = MyClass.customFunction
    method_bp = bluePrintFromMethod("", my_method)
    bp_dict = bluePrintToDict(method_bp)
    reconstructed_bp = bluePrintFromDict(bp_dict)
    assert method_bp == reconstructed_bp







