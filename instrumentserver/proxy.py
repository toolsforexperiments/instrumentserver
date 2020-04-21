# -*- coding: utf-8 -*-
"""
Created on Sat Apr 18 16:13:40 2020

@author: Chao
"""
from typing import Dict, List, Any, Union, Tuple
from qcodes.instrument import parameter
from functools import partial

class InstrumentProxy():
    """Prototype for an instrument proxy object. Each proxy instantiation 
    represents a virtual instrument. 
    
    """
    
    def __init__(self, name: str):
        """ Initialize a proxy. Create a zmq.REQ socket that connectes to the
        server, and get a snapshot from the server. The snapshot will be 
        stroed in a private dictionary.
    
        :param name: The name of the instrument that the proxy will represnt. 
        The name must match the instrument name in the server.
        """
        # This does not include create instrument from client yet
        # Should we just generatea a 'DummyInstrument'?
        self.name = name
        
        self.__paramDict = {
                "ch1" : {"value": 1, "unit" : 'V'},    
                "ch2" : {"value": 2, "unit" : 'V'}    
                }
        
        self.__funcDict = {
                "multiply" : {},
                "reset" : {}
                }
        
        # add all the parameters in the real instrument to this virtual 
        # instrument class
        for paramName_ in self.__paramDict :  
            param_temp = parameter.Parameter(
                            paramName_, 
                            set_cmd = partial(self.setParam, paramName_),
                            get_cmd = partial(self.getParam, paramName_),
                            initial_value = self.__paramDict[paramName_]['value']                             
                            )
            setattr(self, paramName_, param_temp)  
        
        # add all the functions in the real instrument to this virtual 
        # instrument class   
        for funcName_ in self.__funcDict :
            func_temp = partial(self.callFunc, funcName_) 
            setattr(self, funcName_, func_temp ) 
            
        
    # def getParam(self, paraName: str, get: bool = False) -> Any:
    #     """ send requet to the server and get the value of the parameter 
    
    #     :param paraName: The name of the parameter to get
    #     :param get: whether to call `get` on the instrument, if not, the value 
    #         in instrument.snapshot() will be used
    #     """
    #     return self._paramDict[paraName]['value']
    
    def getParam(self, paraName: str) -> Any:
        """ send requet to the server and get the value of the parameter. 
        the request will be a dinctionary in the form of:
            instructionDict = { 
                'name': self.name,                
                'parameters' = {'paramName' : {'value' : None, 'unit' : str}}
                }
                
        :param paraName: The name of the parameter to get
        :returns: the parameter replied from the server
        """
        return self.__paramDict[paraName]['value']
        
    def setParam(self, paraName: str, value: any) -> None: 
        """ send requet to the server and set the value of the parameter 
        the request will be a dinctionary in the form of:
            instructionDict = { 
                'name': self.name,                
                'parameters' = {'paramName' : {'value' : Any, 'unit' : str}}
                } 
        the value can not be None, otherwise will raise TypeError. 
        
        :param paraName: The name of the parameter to set
        """
        self.__paramDict[paraName]['value'] = value
        
    def callFunc(self, funcName: str, *args: Any) -> Any: 
        """ send requet to the server for functioncall
        the request will be a dinctionary in the form of:
            instructionDict = { 
                'name': self.name,                
                'functions' = {'funcName' : args}
                }        
    
        :param funcName: The name of the function to call
        :param args: A tuple that contains the function arguments
        :returns: the return value of the function replied from the server
        """
        if funcName == 'multiply':
            return args[0]*args[1]
        elif funcName == 'reset':
            self.__paramDict['ch1']['value'] = 0
            self.__paramDict['ch2']['value'] = 0
        else:
            raise NotImplementedError
        
        
    def __delete__(self): 
        """ delete class objects and disconnect from server.
        
        """
        