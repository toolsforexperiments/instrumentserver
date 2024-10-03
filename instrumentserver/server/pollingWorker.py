import logging
from typing import Dict, Optional

from .. import QtCore

from ..client import Client
from ..helpers import nestedAttributeFromString

logger = logging.getLogger(__name__)


class PollingWorker(QtCore.QThread):
    def __init__(self, pollingRates: Optional[Dict[str, int]]=None):
        super().__init__(None)
        # This worker is supposed to only run through the server itself so there is no need to change the defaults of the client.
        self.cli = Client()
        self.pollingRates = pollingRates

    # Used by the qtimers, get value of the param
    def getParamValue(self, paramName):
        parts = paramName.split(".")
        instr = self.cli.find_or_create_instrument(parts[0])
        param = parts[1]
        for part in parts[2:]:
            param = param + "." + part
        logger.info(f"{paramName} currently has value {nestedAttributeFromString(instr, param)()}.")

    # Creates a qtimer for each param in the dict with the interval specified
    def run(self):
        timers = []

        # Deletes param from dict if it does not exist
        delList = []
        for param in self.pollingRates:
            if param not in self.cli.getParamDict(param.split(".")[0]):
                logger.warning(f"Parameter {param} does not exist")
                delList.append(param)
        for item in delList:
            del self.pollingRates[item]
        
        # Creates timers for each param in the dict
        for param in self.pollingRates:
            timer = QtCore.QTimer()
            timer.timeout.connect(lambda name=param: self.getParamValue(name))
            timer.start(int(self.pollingRates.get(param) * 1000))
            timers.append(timer)

        self.exec_()
