import zmq
import ruamel.yaml

from pathlib import Path

import datetime
import pandas as pd
import argparse

from instrumentserver.base import recvMultipart
from instrumentserver.blueprints import ParameterBroadcastBluePrint

from abc import ABC, abstractmethod

class Listener(ABC):
    def __init__(self, addr):
        self.addr = addr     

    def run(self):
        # creates zmq subscriber at specified address
        print(f"Connecting to {self.addr}")
        context = zmq.Context()
        socket = context.socket(zmq.SUB)
        socket.connect(self.addr)

        # listen for everything
        socket.setsockopt_string(zmq.SUBSCRIBE, "")

        while True:
            try:
                # parses string message and decodes into ParameterBroadcastBluePrint
                message = recvMultipart(socket)
                self.listenerEvent(message[1])
            except (KeyboardInterrupt, SystemExit):
                # exit if keyboard interrupt
                print("Program Stopped Manually")
                raise

    @abstractmethod
    def listenerEvent(self, message: ParameterBroadcastBluePrint):
        pass

class DFListener(Listener):
    def __init__(self, addr, paramList, path):
        super().__init__(addr)
        self.addr = addr
        self.df = pd.DataFrame(columns=["time","name","value","unit"])
        self.paramList = paramList
        self.path = path

    def run(self):
        super().run()

    def listenerEvent(self, message: ParameterBroadcastBluePrint):
        if message.name in self.paramList:
            self.df.loc[len(self.df)]=[datetime.datetime.now(),message.name,message.value,message.unit]
            self.df.to_csv(self.path)

def loadConfig(path):
    # load config file contents into data
    path = Path(path)
    yaml = ruamel.yaml.YAML(typ='safe')
    data = yaml.load(path)

    # extract address from data
    if 'address' in data:
        addr = data.get('address')
    if 'params' in data:
        paramList = data.get('params')
    if 'csv_path' in data:
        csvPath = data.get('csv_path')
    if 'listener_type' in data:
        type = data.get('listener_type')

    return addr, paramList, csvPath, type
    
def startListener():
    parser = argparse.ArgumentParser(description='Starting the listener')
    parser.add_argument("-p", "--path")
    args = parser.parse_args()

    configPath = Path(args.path)

    # Load variables from config file
    if configPath != '' and configPath is not None:
        addr, paramList, csvPath, type = loadConfig(configPath)
    else:
        print("please enter a valid path for the config file")
        return 0

    if type == "CSV":
        if addr is not None and paramList is not None and csvPath is not None:
            CSVListener = DFListener(addr, paramList, csvPath)
            CSVListener.run()
        else:
            print("Make sure to fill out all fields in config file")
    else:
        print(f"Type {type} not supported")