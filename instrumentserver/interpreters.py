# -*- coding: utf-8 -*-
"""
Created on Mon Apr 20 15:57:23 2020

@author: Chao
"""



from typing import Dict, List, Any, Union
from qcodes import Station
from qcodes.utils.validators import Validator, range_str
import re

def instructionDict_to_instrumentCall(station: Station, instructionDict : Dict) ->  Any:
    """
    This is the interpreter function that the server will call to translate the
    dictionary received from the proxy to instrument calls.
    
    :param station: qcodes.station object, the station that contains the 
        instrument to call.
    :param instructionDict:  The dicitonary passed from the instrument proxy. 
        Must contains a 'name' item whihc is the instrument name.
        And either one of the following:
            a) A dictionary called 'functions' with one item whose key is the 
                name of the function, and the value is a tuple that cantains 
                the values of the function arguments.
                e.g. 
                    functions = {'multiply' : (a, b)}
            b) A dictionary called 'parameters' with one item which is a dictionary
                contains one parameter (qcodes parameter snapshot format). 
                e.g.
                    parameters = {'ch1' : {'value' : 1, 'unit' : V}}
                if value is None, will call 'get parameter', otherwise, set the
                value
    :returns: the parameter returned from the instrument call
    """
    
    instrument = station[instructionDict['name']]
    # if only 'parameters' is in instructionDict and only has one item
    paramName = next(iter(instructionDict['parameters']))
    paramToChange = instructionDict['parameters'][paramName]
    if paramToChange['value'] == None:
        return instrument[paramName]()
    else:
        return instrument[paramName](paramToChange['value'])

    
    # if only 'functions' is in instructionDict and only has one item
    funcName = next(iter(instructionDict['funcs']))
    funcArgs = instructionDict['funcs'][funcName]
    return instrument.call(funcName, *funcArgs)


    

def validatorStr_to_validatorObj(valStr: str) -> Validator:
    """
    This is the interpreter function that translate the validator string back 
    to a Validator object. 
    This can be used in the proxy class for the instantiate of virtual parameters.
    Or in the GUI clients for interface generation.
    
    :param valStr: the string that represents the validator which is generated
        from the snapshot method (parameter.snapshot()['vals'])

    :returns: a Validator object the is easy to use for the goals mentioned above
    """
    # Not fully implemented yet. A very stupid version for now.
    # I have to look into the python re package
    
    # supportedTypes = ['Numbers', 'Strings', 'Boolean']
    # number_type = r"[-+]?\d*\.\d+|\d+"
    # supportedRange = ['=', "<=", '>=']
    #supportedPatterns = []
    def str_to_number(x: str) -> Union[float, int]:
        return float(x) if '.' in x else int(x)
    
    if valStr[:8] ==  '<Numbers':
        if valStr[8] == '>':
            valObj = Numbers()
        elif valStr[9:12] == 'v>='
            valObj = Numbers(str_to_number(valstr[12:-2]))
        elif bool (re.search("<=v", valStr) ):
            valObj = Numbers(str_to_number(valstr[12:-2]))
        
    
    
    