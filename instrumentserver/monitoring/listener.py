import zmq
import ruamel.yaml
import logging
from pathlib import Path

from datetime import datetime, timezone, timedelta
import pandas as pd
import argparse
import os.path

from instrumentserver.base import recvMultipart
from instrumentserver.blueprints import ParameterBroadcastBluePrint
from typing import Dict, Any

from abc import ABC, abstractmethod

from influxdb_client import InfluxDBClient, Point, WriteOptions

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

class Listener(ABC):
    def __init__(self, addresses: list):
        self.addresses = addresses     

    def run(self):

        # creates zmq subscriber at specified address
        logger.info(f"Connecting to {self.addresses}")
        context = zmq.Context()
        socket = context.socket(zmq.SUB)

        # listen at all the addresses
        for addr in self.addresses:
            socket.connect(addr)

            # listen for everything
            socket.setsockopt_string(zmq.SUBSCRIBE, "")

            logger.info(f"Listener Connected to {addr}")

        listen = True

        try:
            while listen:
                try:
                    # parses string message and decodes into ParameterBroadcastBluePrint
                    message = recvMultipart(socket)
                    self.listenerEvent(message[0],message[1])
                except (KeyboardInterrupt, SystemExit):
                    # exit if keyboard interrupt
                    logger.info("Program Stopped Manually")
                    raise
        finally:
            socket.close()

    @abstractmethod
    def listenerEvent(self, message: ParameterBroadcastBluePrint):
        pass

class DFListener(Listener):
    def __init__(self, addresses: list, paramList: list, path: str):
        super().__init__(addresses)
        self.addresses = addresses
        self.path = path

        # checks if data file already exists
        # if it does, reads the file to make the appropriate dataframe
        if os.path.isfile(self.path):
            self.df = pd.read_csv(self.path)
            self.df = self.df.drop("Unnamed: 0", axis=1)
        else:
            self.df = pd.DataFrame(columns=["time","name","value","unit"])

        self.paramList = list(paramList)

    def run(self):
        super().run()

    def listenerEvent(self, message: ParameterBroadcastBluePrint):
        
        # listens only for parameters in the list, if it is empty, it listens to everything
        if not self.paramList:
            logger.info(f"Writing data [{message.name},{message.value},{message.unit}]")
            self.df.loc[len(self.df)]=[datetime.datetime.now(),message.name,message.value,message.unit]
            self.df.to_csv(self.path)
        elif message.name in self.paramList:
            logger.info(f"Writing data [{message.name},{message.value},{message.unit}]")
            self.df.loc[len(self.df)]=[datetime.datetime.now(),message.name,message.value,message.unit]
            self.df.to_csv(self.path)

class InfluxListener(Listener):

    def __init__(self, addresses: list, paramList: list, token: str, org: str, bucketDict: Dict[str,str], url: str, measurementNameDict: Dict[str,str]):
        super().__init__(addresses)

        self.addresses = addresses
        self.token = token
        self.org = org
        self.bucketDict = bucketDict
        self.url = url
        self.paramList = list(paramList)
        self.measurementNameDict = measurementNameDict

        self.client = InfluxDBClient(url=self.url, token=self.token, org=self.org)
        self.write_api = self.client.write_api(write_options=WriteOptions(batch_size=1))

        timezone_offset = -6.0  # Central Standard Time (UTC−06:00)
        self.timezoneInfo = timezone(timedelta(hours=timezone_offset))

    def run(self):
        super().run()

    def listenerEvent(self, instrument, message: ParameterBroadcastBluePrint):
        bucket = self.bucketDict[instrument]
        measurementName = self.measurementNameDict[instrument]
        # listens only for parameters in the list, if it is empty, it listens to everything
        if not self.paramList or message.name in self.paramList:
            logger.info(f"Writing data [{message.name},{message.value},{message.unit}]")
            point = Point(measurementName).tag("name", message.name)
            try :
                point = point.field("value", float(message.value))
            except ValueError:
                point = point.field("value_string", message.value)
            point = point.time(datetime.now(self.timezoneInfo))
            self.write_api.write(bucket=bucket, org=self.org, record=point)


def checkInfluxConfig(configInput: Dict[str, Any]):

    # check if all fields are present in the config file
    influxFields = ['addresses', 'params', 'token', 'org', 'bucketDict', 'url', 'measurementNameDict']
    for field in influxFields:
        if field not in configInput or configInput[field] is None:
            logger.info(f"Missing field {field} in config file")
            return False
    if 'measurementName' not in configInput or configInput['measurementName'] is None:
        configInput['measurementName'] = 'my_measurement'
    return True

def checkCSVConfig(configInput: Dict[str, Any]):

    # check if all fields are present in the config file
    csvField = ["addresses", "params", "csv_path"]
    for field in csvField:
        if field not in configInput or configInput[field] is None:
            logger.info(f"Missing field {field} in config file")
            return False
    return True

def startListener():

    parser = argparse.ArgumentParser(description='Starting the listener')
    parser.add_argument("-c", "--config")
    args = parser.parse_args()

    configPath = Path(args.config)
    yaml = ruamel.yaml.YAML()

    # load variables from config file
    if configPath != '' and configPath is not None:
        configInput = yaml.load(configPath)
    else:
        logger.warning("Please enter a valid path for the config file")
        return 0

    # start listener that writes to CSV or Influx Database
    if 'type' in configInput: 
        if configInput['type'] == "CSV":
            if checkCSVConfig(configInput):
                CSVListener = DFListener(configInput['addresses'], configInput['params'], configInput['csv_path'])
                CSVListener.run()
        elif configInput['type'] == "Influx": 
            if checkInfluxConfig(configInput):
                DBListener = InfluxListener(configInput['addresses'], configInput['params'], configInput['token'], configInput['org'], configInput['bucketDict'], configInput['url'], configInput['measurementNameDict'])
                DBListener.run()
        else:
            logger.warning(f"Type {configInput['type']} not supported")
    else:
        logger.warning("Please enter a valid type in the config file")