"""
=========
logger.py
=========

The center class of this file is the ParameterLogger class which start based on the 
"""
import datetime
import os
from typing import Optional, Dict
import logging

import pandas as pd
from .. import QtCore

from ..client import Client
from ..client import SubClient
from . import read_config

logger = logging.getLogger(__name__)

class LoggerParameter:
    """
    Holds the different parameters the logger is tracking. It holds all the metadata as well as fresh data

    :param name: Name of the parameter
    :param source_type: Specifies how to gather the data for the parameter (parameter or broadcast)
    :param parameter_path: Full name with submodules of the qcodes parameter
    :param client: InstrumentClient, which the instance used to communicate with the server
    :param server: Location of the server, defaults to 'localhost'
    :param port: Port of the server, defaults to 5555
    :param interval: Interval of time to gather new updates in seconds,
                     only impactful if source_type is of the parameter type. defaults to 1.
    """

    def __init__(self, name: str,
                 source_type: str,
                 parameter_path: str,
                 client: Client,
                 server: Optional[str] = 'localhost',
                 port: Optional[int] = 5555,
                 interval: Optional[int] = 1):
        # load values
        self.name = name
        self.source_type = source_type
        self.parameter_path = parameter_path
        self.client = client
        self.server = server
        self.port = port
        self.interval = interval

        # data container
        self.data = []
        self.time = []

        # form the address
        self.address = f"tcp://{self.server}:{self.port}"

        # locate the instrument this parameter is located
        submodules = parameter_path.split('.')
        self.instrument_name = submodules[0]
        self.instrument = self.client.get_instrument(self.instrument_name)

        # get the name of the parameter with submodules
        parameter_name = ''
        for i in range(1, len(submodules)):
            parameter_name = parameter_name + submodules[i]
        self.parameter_name = parameter_name

        # record the time the parameter was created
        self.last_saved_t = datetime.datetime.now()

        if source_type == 'broadcast':
            self.broadcastInitiation()

    def broadcastInitiation(self):
        """
        Initialize the data when the source type is broadcast.
        """
        new_data = self.instrument.get(self.parameter_name)
        current_time = datetime.datetime.now()
        self.data.append(new_data)
        self.time.append(current_time)

    def update(self, data=None):
        """
        Updates the parameter and save a new data point in memory
        :param data: this parameter is used to manually input data into the parameter. Can only be used when type set to
        broadcast
        """

        # check that the source type is parameter
        if self.source_type == 'parameter':

            # gather new client data and save it in memory
            new_data = self.instrument.get(self.parameter_name)
            current_time = datetime.datetime.now()
            self.data.append(new_data)
            self.time.append(current_time)

        if self.source_type == 'broadcast':
            current_time = datetime.datetime.now()
            self.data.append(data)
            self.time.append(current_time)
            pass


class ParameterLogger(QtCore.QObject):
    """
    Main class of the logger. All the parameters are saved inside this class

    :param config: The dictionary from the config file.
    """

    def __init__(self, config: Dict):
        super().__init__()

        # store the parameters
        self.active_parameters = []
        self.passive_parameters = []

        # store the clients
        self.clients = {}  # in the format of {'server': {'port': client}}

        # store the sub_clients
        self.sub_clients = {}
        self.sub_threads = {}

        # read the config file
        parameters, refresh, save_directory = read_config('logger', config)

        # create the LoggerParameters based on the config file
        for params in parameters:
            name = params[0]
            source_type = params[1]
            parameter_path = params[2]
            server = params[3]
            port = params[4]
            interval = params[5]
            if source_type == "parameter":
                self._checkIfContainClient(server, port)  # create the client if not have yet
                self.active_parameters.append(LoggerParameter(name=name,
                                                              source_type=source_type,
                                                              parameter_path=parameter_path,
                                                              client=self.clients[server][port],
                                                              server=server, port=port,
                                                              interval=interval))

            else:
                self._checkIfContainSubClient(server, port)  # create the sub client if not have yet
                self._checkIfContainClient(server, port - 1)
                self.passive_parameters.append(LoggerParameter(name=name,
                                                               source_type=source_type,
                                                               parameter_path=parameter_path,
                                                               client=self.clients[server][port-1],
                                                               server=server, port=port,
                                                               interval=interval))
        # check if the values are none.
        # if they are set the default one, if not, set the specified one in the config file
        if refresh is not None:
            self.refresh = refresh
        else:
            self.refresh = 10

        if save_directory is not None:
            self.save_directory = save_directory
        else:
            self.save_directory = os.path.join(os.getcwd(), 'dashboard_data.csv')

        self.active = False
        self.last_saved_t = datetime.datetime.now()
        self.timer = QtCore.QTimer(self)

    def saveData(self):
        """
        Saves the data in the specified file indicated in the config dictionary. Deletes the data stored in the
        parameter once it has been saved to storage.
        """
        # go through the parameters and create DataFrames with their data
        logger.info(f"Saving Data")
        df_list = []
        for params in self.active_parameters:
            holder_df = pd.DataFrame({'time': params.time,
                                      'value': params.data,
                                      'name': params.name,
                                      'parameter_path': params.parameter_path,
                                      'address': params.address
                                      })
            df_list.append(holder_df)
            params.data = []
            params.time = []

        for params in self.passive_parameters:
            holder_df = pd.DataFrame({'time': params.time,
                                      'value': params.data,
                                      'name': params.name,
                                      'parameter_path': params.parameter_path,
                                      'address': params.address
                                      })
            df_list.append(holder_df)
            params.data = []
            params.time = []

        ret = pd.concat(df_list, ignore_index=True)

        # check if the file already exist, if it does not include the header in the saving.
        if not os.path.exists(self.save_directory):
            ret.to_csv(self.save_directory, index=False, mode='a')
        else:
            ret.to_csv(self.save_directory, index=False, mode='a', header=False)

    def runLogger(self):
        """
        Start The timer. Constantly running and checking if it is time to either save data or collect new data.
        """
        self.active = True

        self.timer.timeout.connect(self._loggerDrive)
        self.timer.start(1000)
        logger.info(f"Logger Start")
        self._startSubClients()

        return

    def _loggerDrive(self):
        """
        This method update the all the active parameter by calling their client.
        """
        if self.active:
            # checks what is the current time
            current_t = datetime.datetime.now()

            # check if its time to save data
            if (current_t - self.last_saved_t).total_seconds() >= self.refresh:
                self.saveData()
                self.last_saved_t = current_t

            # individually check if its time to collect data from each parameter
            for params in self.active_parameters:
                if (current_t - params.last_saved_t).total_seconds() >= params.interval:
                    params.update()
                    params.last_saved_t = current_t
        else:
            self.timer.stop()

    @QtCore.Slot(dict)
    def onSubSlot(self, list_message):
        """
        This method is a slot that will be called by the subClients if they received a message. This should be connected
        to the SubClient.update_logger.
        :param list_message: A dictionary that contains the information received.
        """
        server = list_message['server']
        port = list_message['port']
        message = list_message
        action = message['action']
        if action == 'parameter-call' or action == 'parameter-update':
            name = message['name']
            value = message['value']

            if self._checkIfContainSubParameter(server, port, name):
                self._getSubParameter(server, port, name).update(data=value)

        pass

    def _checkIfContainClient(self, server, port, create_client=True):
        """
        This method checks if the class contains the client with the provided server and port and can create a client
        instance if it does not exist.
        :param server: the server string
        :param port: the port number
        :param create_client: whether to create a client if the client does not exist for provided server and port
        :return: if target exist
        """
        if server in self.clients and port in self.clients[server]:
            return True
        elif create_client:
            if server not in self.clients:
                self.clients[server] = {}
            self.clients[server][port] = Client(host=server, port=port)
            return True
        return False

    def _checkIfContainSubClient(self, server, port, create_client=True):
        """
        This method checks if the class contains the subClient with the provided server and port and can create a
        SubClient instance if it does not exist.
        :param server: the server string
        :param port: the port number
        :param create_client: whether to create a subclient if the subclient does not exist for provided server and port
        :return: if target exist
        """
        if server in self.sub_clients and port in self.sub_clients[server]:
            return True
        elif create_client:
            if server not in self.sub_clients:
                self.sub_clients[server] = {}
                self.sub_threads[server] = {}
            self.sub_clients[server][port] = SubClient(sub_host=server, sub_port=port, logger_mode=True)
            self.sub_threads[server][port] = QtCore.QThread()
            self.sub_clients[server][port].moveToThread(self.sub_threads[server][port])
            self.sub_threads[server][port].started.connect(self.sub_clients[server][port].connect)
            self.sub_clients[server][port].update_logger.connect(self.onSubSlot)
            return True
        return False

    def _checkIfContainSubParameter(self, server, port, parameter_path):
        """
        This method checks if the class contains the passive parameter with the provided server, port and
        parameter_path.
        :param server: server string
        :param port: port number
        :param parameter_path: parameter path
        :return: if target exist
        """
        for parameter in self.passive_parameters:
            if parameter.server == server and parameter.port == port and parameter.parameter_path == parameter_path:
                return True
        return False

    def _getSubParameter(self, server, port, parameter_path):
        """
        Return the passive parameter.
        :param server: server string
        :param port: port number
        :param parameter_path: parameter path
        :return: target parameter
        """
        for parameter in self.passive_parameters:
            if parameter.server == server and parameter.port == port and parameter.parameter_path == parameter_path:
                return parameter
        return

    def _startSubClients(self):
        """
        Start all the SubClients
        """
        for server in self.sub_clients:
            for port in self.sub_clients[server]:
                self.sub_threads[server][port].start()
                print(f'[SubClient Start]: Server: {server}, Port: {port}')

        pass
