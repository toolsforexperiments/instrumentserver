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


def combo_label_lineEdit(widget, labelList, startX=0, startY=0):
    """Summary
    
    Parameters
    ----------
    widget : TYPE
        Description
    labelList : TYPE
        Description
    startX : int, optional
        Description
    startY : int, optional
        Description
    
    Returns
    -------
    TYPE
        Description
    
    Raises
    ------
    ValueError
        Description
    """
    _translate = QtCore.QCoreApplication.translate
    gridLayout = QtWidgets.QGridLayout(widget)
    gridLayout.setContentsMargins(0, 0, 0, 0)
    gridLayout.setHorizontalSpacing(10)
    gridLayout.setVerticalSpacing(10)

    if labelList.shape[1] % 2 != 0:
        raise ValueError('each label should also include lineEdit default name (could be "")')
    row_ = labelList.shape[0]
    column_ = labelList.shape[1]

    lineEidtMatrix = np.empty((row_, int(column_/2)), dtype=object)

    for i in range(row_):
        for j in range(int(column_/2)):
            if labelList[i, 2 * j] == '':
                pass
            else:
                label = QtWidgets.QLabel(widget)
                label.setFont(fontFunc('Arial', 12))
                label.setText(_translate("GUI", labelList[i, 2 * j]))
                gridLayout.addWidget(label, startX + i, startY + 2 * j, 1, 1)

                lineEdit = QtWidgets.QLineEdit(widget)
                lineEdit.setClearButtonEnabled(True)
                lineEdit.setFont(fontFunc('Arial', 10))
                lineEdit.setFixedWidth(200)
                lineEdit.setFixedHeight(40)
                lineEdit.setText(_translate("GUI", labelList[i, 2 * j + 1]))
                gridLayout.addWidget(lineEdit, startX + i, startY + 2 * j + 1, 1, 1)
                lineEidtMatrix[i, j] = lineEdit
    return gridLayout, lineEidtMatrix


def createAllProjectsDir():
    try:
        with open('./static/allProjects.json', 'r') as jsonOpen_:
            jsonOpen = json.load(jsonOpen_)
            fatherList= list(jsonOpen.keys())
            for fatherName in fatherList:
                for sonDic in jsonOpen[fatherName]:
                    directory_ = sonDic['directory']
                    name_ = sonDic['name']        
                    project_ = sonDic['project']     
                    version_ = sonDic['version']
                    fridgeName_ = sonDic['fridgeName']
                    date_ = sonDic['date']
                    dir_ = directory_ + name_ + "\\" + project_ + "_" + version_ + "\\" + fridgeName_ + "_" + date_ + "\\"
                    try:
                        os.makedirs(dir_)
                    except FileExistsError:
                        pass
    except FileNotFoundError:
        pass


def jsonToDict_TypeOrder(filename):
    """Change the instrument json file into type order dictionary in python.
    
    Parameters
    ----------
    filename : string
        Json file of all the instruments can be controlled.
    
    Returns
    -------
    len(dict_) : int
        number of instruments.
    
    newInstDict : dictionary
        Type order instrument dictionary.
    
    """
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

    return len(dict_["instruments"]), newInstDict


if __name__ == '__main__':
    createAllProjectsDir()
    # num, dictionary = jsonToDict_TypeOrder("instrJson.json")
