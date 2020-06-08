# -*- coding: utf-8 -*-
"""
Created on Fri Apr 24 10:01:21 2020

@author: Pinlei
"""

import os
import numpy as np
import sys
import json
from qtpy import QtGui, QtCore, QtWidgets
from qtpy.QtWidgets import *
from qtpy.QtGui import *


def fontFunc(fontName, size, **kwargs):
    """Automatically generate font in qt5
    
    Parameters
    ----------
    fontName : string
        eg: "Arial"...
    size : int (0-100)
        font size
    **kwargs
        Following the setting from QtGui.QFont
    
    Returns
    -------
    QtGui.QFont
        The font can be used in the qt5
    """
    weight_ = kwargs.get("weight", 50)
    font = QtGui.QFont()
    font.setFamily(fontName)
    font.setPointSize(size)
    font.setWeight(weight_)
    return font