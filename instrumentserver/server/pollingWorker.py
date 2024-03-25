import logging
from .. import QtCore
from ..client import Client

logger = logging.getLogger(__name__)

class PollingWorker(QtCore.QThread):
    def __init__(self):
        super().__init__(None)
        self.cli = Client()
        self.pollingRatesDict = {}

    # Used by the qtimers, get value of the param
    def getParamValue(self, paramName):
        logger.info(f"{paramName} currently has value {self.cli.getParamDict(paramName.split('.')[0]).get(paramName)}.")

    # Used by apps.py, passes the list of params with their respective polling rates
    def setPollingDict(self, pollingDict):
        self.pollingRatesDict = pollingDict

    # Creates a qtimer for each param in the dict with the interval specified
    def run(self):
        timers = []

        # Deletes param from dict if it does not exist
        delList = []
        for param in self.pollingRatesDict:
            if param not in self.cli.getParamDict(param.split(".")[0]):
                logger.warn(f"Parameter {param} does not exist")
                delList.append(param)
        for item in delList:
            del self.pollingRatesDict[item]
        
        # Creates timers for each param in the dict
        for param in self.pollingRatesDict:
            timer = QtCore.QTimer()
            timer.timeout.connect(lambda name=param: self.getParamValue(name))
            timer.start(self.pollingRatesDict.get(param)*1000)
            timers.append(timer)
        self.exec_()