"""
=========
logger.py
=========

The center class of this file is the ParameterLogger class which start based on the 
"""
import datetime
import os
from typing import Optional, Dict

import pandas as pd
from .. import QtCore

from ..client import Client
from ..client import SubClient
from . import read_config


class LoggerParameter:
    """
    Holds the different parameters the logger is tracking. It holds all the metadata as well as fresh data.

    :param name: Name of the parameter.
    :param source_type: Specifies how to gather the data for the parameter (parameter or broadcast).
    :param parameter_path: Full name with submodules of the qcodes parameter.
    :param client: InstrumentClient, which the instance used to communicate with the server
    :param server: Location of the server, defaults to 'localhost'.
    :param port: Port of the server, defaults to 5555.
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
            self.broadcast_initiation()
            print(self.data)

    def broadcast_initiation(self):
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
                self._check_if_contain_client(server, port)  # create the client if not have yet
                self.active_parameters.append(LoggerParameter(name=name,
                                                              source_type=source_type,
                                                              parameter_path=parameter_path,
                                                              client=self.clients[server][port],
                                                              server=server, port=port,
                                                              interval=interval))

            else:
                self._check_if_contain_sub_client(server, port)  # create the sub client if not have yet
                self._check_if_contain_client(server, port-1)
                self.passive_parameters.append(LoggerParameter(name=name,
                                                               source_type=source_type,
                                                               parameter_path=parameter_path,
                                                               client=self.clients[server][port-1],
                                                               server=server, port=port,
                                                               interval=interval))
        print(self.passive_parameters)
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

    def save_data(self):
        """
        Saves the data in the specified file indicated in the config dictionary.
        Deletes the data from memory once it has been saved to storage.
        """
        # go through the parameters and create DataFrames with their data
        print('[Saving Data]')
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

    def run_logger(self):
        """
        Start The timmer. Constantly running checking if its time to either save data or collect new data.
        """
        self.active = True

        self.timer.timeout.connect(self._logger_drive)
        self.timer.start(1000)
        print(f'[Logger Start]')
        self._start_sub_clients()

        return

    def _logger_drive(self):
        """
        This method update the all the active parameter by calling the their client.
        """
        print(f'[Logger Drive]')
        if self.active:
            # checks what is the current time
            current_t = datetime.datetime.now()

            # check if its time to save data
            if (current_t - self.last_saved_t).total_seconds() >= self.refresh:
                self.save_data()
                self.last_saved_t = current_t

            # individually check if its time to collect data from each parameter
            for params in self.active_parameters:
                if (current_t - params.last_saved_t).total_seconds() >= params.interval:
                    params.update()
                    params.last_saved_t = current_t
        else:
            self.timer.stop()

    @QtCore.Slot(dict)
    def sub_slot(self, list_message):
        """
        This method is a slot that will be called by the subclients if they received a message. This should be connected
        to the SubClient.update_logger.
        """
        server = list_message['server']
        port = list_message['port']
        message = list_message
        action = message['action']
        if action == 'parameter-call' or action == 'parameter-update':
            name = message['name']
            value = message['value']

            if self._check_if_contain_sub_parameter(server, port, name):
                print(f'[SubParameter Update]: Server: {server}, Port: {port}, Param: {name}, value: {value}')
                self._get_sub_parameter(server, port, name).update(data=value)

        pass

    def _check_if_contain_client(self, server, port, create_client=True):
        if server in self.clients and port in self.clients[server]:
            return True
        elif create_client:
            if server not in self.clients:
                self.clients[server] = {}
            self.clients[server][port] = Client(host=server, port=port)
            return True
        return False

    def _check_if_contain_sub_client(self, server, port, create_client=True):
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
            self.sub_clients[server][port].update_logger.connect(self.sub_slot)
            return True
        return False

    def _check_if_contain_sub_parameter(self, server, port, parameter_path):
        for parameter in self.passive_parameters:
            if parameter.server == server and parameter.port == port and parameter.parameter_path == parameter_path:
                return True
        return False

    def _get_sub_parameter(self, server, port, parameter_path):
        for parameter in self.passive_parameters:
            if parameter.server == server and parameter.port == port and parameter.parameter_path == parameter_path:
                return parameter
        return

    def _start_sub_clients(self):
        for server in self.sub_clients:
            for port in self.sub_clients[server]:
                self.sub_threads[server][port].start()
                print(f'[SubClient Start]: Server: {server}, Port: {port}')

        pass
