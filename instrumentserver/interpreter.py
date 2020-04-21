# -*- coding: utf-8 -*-
"""
Created on Mon Apr 20 15:57:23 2020

@author: Chao
"""



from typing import Dict, List, Any, Union
from qcodes import Station

def dict_to_instrument_call(station: Station, instructionDict : Dict) ->  Any:
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