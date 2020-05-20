"""package for data processing.

0519_2020, Pinlei Lu
"""
import h5py
import matplotlib.pyplot as plt
import datetime
import os
import numpy as np
import json

class dataProcess():

    """class for data saving. It will also create identifier for the future lookup
    
    Attributes:
        cwd (str): main directory for saving
        dateStr (str): date, default is today
        dirInfo (dict): dictionary for store the saving information
        dirSave (str): the final directory that saved the file
        fileName (str): saved file's name
        identifier (str): Each file have been save will have an unique number to checkup later
        msmtName (str): generally will be the measurement code name
        paramDict (dict): the condition that data takes
        peopleName (str): people name who created the file
        projectName (str): the project which is going on
        rawData (TYPE): the data you want to save
        saveName (str): the final save name; Notice: this may be different than the original name due to the conflict.
    """
    
    def __init__(self, dirInfo: dict, fileName: str, rawData, paramDict: dict):
        """For initialize the class, input directory, filename, rawData and parameter condition.
        
        Args:
            dirInfo (dict): dictionary for store the saving information
            fileName (str): saved file's name
            rawData (TYPE): the data you want to save
            paramDict (dict): the condition that data takes
        """
        self.dirInfo = dirInfo
        self.fileName = fileName
        self.rawData = rawData
        self.paramDict = paramDict
        self.extraItem = {}

    def createDir(self):
        """Create directory if this is the first time.

        """
        self.cwd = self.dirInfo.get("cwd", "D://Data//")
        self.peopleName = self.dirInfo.get("peopleName", "Others")
        self.projectName = self.dirInfo.get("projectName", "Project")
        self.msmtName = self.dirInfo.get("msmtName", "msmt")
        self.dateStr = self.dirInfo.get("date", datetime.date.today().strftime('%Y_%m%d'))
        self.dirSave = self.cwd + self.peopleName + "/" + self.projectName + "/" + self.msmtName + "/" + self.dateStr + '/'
        try:
            os.makedirs(self.dirSave)
        except FileExistsError:
            print("Directory exists, continue.")

    def addSaveItem(self, itemName: str, data_):
        """Add more items to save (sweeping parameter, etc.)
        
        Args:
            itemName (str): the name of itme you want to save
            data_ (TYPE): data, generally should be numpy array
        
        """
        self.extraItem[itemName] = data_

    def saveData(self):
        """Save data, if already exists, will add index after.

        """
        save = True
        index = 1
        saveName = self.fileName
        while save:
            try:
                fileOpen = h5py.File(self.dirSave + saveName, 'w-')
                save = False
            except IOError:
                saveName = self.fileName + '_' + str(index)
            index += 1
        fileOpen.create_dataset('rawData', data=self.rawData)
        fileOpen.create_dataset('paramDict', data=str(self.paramDict))
        for item in self.extraItem.keys():
            fileOpen.create_dataset(item, data=self.extraItem[item])
        fileOpen.close()
        self.saveName = saveName

    def createIdentifier(self):
        """Create identifier for lookup later
        
        Returns:
            str: identification number
        """
        idStr = self.peopleName[0:2] + self.projectName[0:2] + self.msmtName[0:2]
        idIndex = 0
        identifier = idStr + str(idIndex).zfill(6)

        fileDict = {"identifier": identifier,
                    "saveDir": self.dirSave,
                    "filename": self.saveName,
                    "paramDict": self.paramDict}

        jsonFileName = self.cwd + self.peopleName + "/" + self.projectName + "/" + 'allFiles.json' 
        allFiles = {}
        save = False
        while not save:
            try:
                with open(jsonFileName, 'r+') as jsonSave:
                    jsonOpen = json.load(jsonSave)
                    if identifier in list(jsonOpen.keys()):
                        idIndex += 1
                        identifier = idStr + str(idIndex).zfill(6)
                    else:
                        fileDict["identifier"] = identifier
                        jsonOpen[identifier] = fileDict
                        save = True

                with open(jsonFileName, 'w') as jsonSave:
                    json.dump(jsonOpen, jsonSave)

            except FileNotFoundError:
                with open(jsonFileName, 'w') as jsonSave:
                    json.dump({identifier: [fileDict]}, jsonSave)
                save = True
        self.identifier = identifier
        return self.identifier

    def save(self):
        """(main execution) Save files and also identifier.

        """
        self.createDir()
        self.saveData()
        self.createIdentifier()

class dataPlot():
    def __init__():
        return

    def livePlotStart():
        return

    def livePlotAdd():
        return

    def livePlotEnd():
        return

    def singlePlot():
        return

    def plotSave():
        return


if __name__ == '__main__':

    dirInfo = {"cwd": "D://Data//",
               "peopleName": "Pinlei",
               "projectName": "SNAIL",
               "msmtName": "GainSweep"}

    sv = dataProcess(dirInfo, 'test', np.arange(100), dirInfo)
    sv.save()
