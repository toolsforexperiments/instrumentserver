import argparse
import logging
import os.path
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict

import pandas as pd
import pytz
import ruamel.yaml  # type: ignore[import-untyped] # Known bugfix under no-fix status: https://sourceforge.net/p/ruamel-yaml/tickets/328/
import zmq
try:
    from influxdb_client import InfluxDBClient, Point, WriteOptions
except ImportError:
    pass

from instrumentserver.base import recvMultipart
from instrumentserver.blueprints import ParameterBroadcastBluePrint

logging.basicConfig(level=logging.INFO)
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


@dataclass
class CSVConfig:
    addresses: list
    params: list
    csv_path: str

    @classmethod
    def from_dict(cls, config_dict):
        return cls(
            addresses=config_dict['addresses'],
            params=config_dict['params'],
            csv_path=config_dict['csv_path']
        )
    
@dataclass
class InfluxConfig:
    addresses: list
    params: list
    token: str
    org: str
    bucketDict: Dict[str,str]
    url: str
    measurementNameDict: Dict[str,str]
    timezone_name: str = 'CDT'

    @classmethod
    def from_dict(cls, config_dict):
        return cls(
            addresses=config_dict['addresses'],
            params=config_dict['params'],
            token=config_dict['token'],
            org=config_dict['org'],
            bucketDict=config_dict['bucketDict'],
            url=config_dict['url'],
            measurementNameDict=config_dict['measurementNameDict']
        )


class DFListener(Listener):
    def __init__(self, csvConfig: CSVConfig):
        super().__init__(csvConfig.addresses)
        self.addresses = csvConfig.addresses
        self.path = csvConfig.csv_path

        # checks if data file already exists
        # if it does, reads the file to make the appropriate dataframe
        if os.path.isfile(self.path):
            self.df = pd.read_csv(self.path)
            self.df = self.df.drop("Unnamed: 0", axis=1)
        else:
            self.df = pd.DataFrame(columns=["time","name","value","unit"])

        self.paramList = list(csvConfig.params)

    def run(self):
        super().run()

    def listenerEvent(self, message: ParameterBroadcastBluePrint):
        
        # listens only for parameters in the list, if it is empty, it listens to everything
        if not self.paramList:
            logger.info(f"Writing data [{message.name},{message.value},{message.unit}]")
            self.df.loc[len(self.df)]=[datetime.now(),message.name,message.value,message.unit]
            self.df.to_csv(self.path)
        elif message.name in self.paramList:
            logger.info(f"Writing data [{message.name},{message.value},{message.unit}]")
            self.df.loc[len(self.df)]=[datetime.now(),message.name,message.value,message.unit]
            self.df.to_csv(self.path)

class InfluxListener(Listener):

    def __init__(self, influxConfig: InfluxConfig):
        super().__init__(influxConfig.addresses)

        self.addresses = influxConfig.addresses
        self.token = influxConfig.token
        self.org = influxConfig.org
        self.bucketDict = influxConfig.bucketDict
        self.url = influxConfig.url
        self.paramList = list(influxConfig.params)
        self.measurementNameDict = influxConfig.measurementNameDict

        self.client = InfluxDBClient(url=self.url, token=self.token, org=self.org)
        self.write_api = self.client.write_api(write_options=WriteOptions(batch_size=1))

        self.timezone_info = get_timezone_info(influxConfig.timezone_name)

    def run(self):
        super().run()

    def listenerEvent(self, instrument, message: ParameterBroadcastBluePrint):
        bucket = self.bucketDict[instrument]
        measurementName = self.measurementNameDict[instrument]
        # listens only for parameters in the list, if it is empty, it listens to everything
        if not self.paramList or message.name in self.paramList:
            logger.info(f"Writing data [{message.name},{message.value},{message.unit}]")
            point = Point(measurementName).tag("name", message.name)
            try:
                point = point.field("value", float(str(message.value)))
            except ValueError:
                point = point.field("value_string", message.value)
            point = point.time(datetime.now(self.timezone_info))
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

def get_timezone_info(timezone_name):
    try:
        tz = pytz.timezone(timezone_name)
        return tz
    except pytz.UnknownTimeZoneError:
        print(f"Unknown timezone: {timezone_name}")
        return None
    

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
                CSVListener = DFListener(CSVConfig.from_dict(configInput))
                CSVListener.run()
        elif configInput['type'] == "Influx": 
            if checkInfluxConfig(configInput):
                DBListener = InfluxListener(InfluxConfig.from_dict(configInput))
                DBListener.run()
        else:
            logger.warning(f"Type {configInput['type']} not supported")
    else:
        logger.warning("Please enter a valid type in the config file")