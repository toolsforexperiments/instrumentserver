# -*- coding: utf-8 -*-
"""
Created on Fri Apr 24 10:01:21 2020

@author: Pinlei
"""

import sys
import json
from qtpy import QtGui, QtCore, QtWidgets
from qtpy.QtWidgets import *
from qtpy.QtGui import *


def jsonToDict_TypeOrder(filename):
    '''
    Change the instrument json file into type order dictionary in python.

    Parameters
    ----------
    filename : string
        Json file of all the instruments can be controlled.

    Returns
    -------
    newInstDict : dictionary
        Type order instrument dictionary.

    '''
    with open(filename) as j:
        dict_ = json.load(j)
    
    newInstDict = {}
    for inst_ in dict_['instruments']:
        dict_['instruments'][inst_]['instrName'] = inst_
        type_ = dict_['instruments'][inst_]['type']
        if type_  in newInstDict:
            newInstDict[type_].append(dict_['instruments'][inst_])
        else:
            newInstDict[type_] = [dict_['instruments'][inst_]]

    return newInstDict


if __name__ == '__main__':
    dictionary = jsonToDict_TypeOrder("instrJson.json")