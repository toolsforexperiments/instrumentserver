import datetime
import os
from typing import Optional, List

import pandas as pd
from .. import QtCore

from ..client import Client as InstrumentClient

from .__init__ import read_config


class LoggerParameters:
    """
    Holds the different parameters the logger is tracking. It holds all of the metadata as well as fresh data

    :param name: Name of the parameter.
    :param source_type: Specifies how to gather the data for the parameter (parameter or broadcast).
    :param parameter_path: Full name with submodules of the qcodes parameter.
    :param server: Location of the server, defaults to 'localhost'.
    :param port: Port of the server, defaults to 5555.
    :param interval: Interval of time to gather new updates in seconds,
                     only impactful if source_type is of the parameter type. defaults to 1.
    """

    def __init__(self, name: str,
                 source_type: str,
                 parameter_path: str,
                 server: Optional[str] = 'localhost',
                 port: Optional[int] = 5555,
                 interval: Optional[int] = 1):

        # load values
        self.name = name
        self.source_type = source_type
        self.parameter_path = parameter_path
        self.server = server
        self.port = port
        self.address = f"tcp://{self.server}:{self.port}"
        self.interval = interval

        self.data = []
        self.time = []

        # locate the instrument this parameter is located
        submodules = parameter_path.split('.')
        self.instrument_name = submodules[0]
        self.client = InstrumentClient(self.server, self.port)
        self.instrument = self.client.get_instrument(self.instrument_name)

        # get the name of the parameter with submodules
        parameter_name = ''
        for i in range(1, len(submodules)):
            parameter_name = parameter_name + submodules[i]
        self.parameter_name = parameter_name

        # record the time the parameter was created
        self.last_saved_t = datetime.datetime.now()

    def update(self):
        """
        Updates the parameter and save a new data point in memory
        """

        # check that the source type is parameter
        if self.source_type == 'parameter':

            # just for development
            self.instrument.generate_data(self.parameter_name)

            # gather new data and save it in memory
            new_data = self.instrument.get(self.parameter_name)
            current_time = datetime.datetime.now()
            self.data.append(new_data)
            self.time.append(current_time)

        if self.source_type == 'broadcast':
            raise NotImplementedError


class ParameterLogger(QtCore.QObject):
    """
    Main class of the logger. All of the parameters are saved inside this class
    """
    def __init__(self):
        super().__init__()

        # used for testing, the instruments should be already created for the dashboard to work
        cli = InstrumentClient()

        if 'test' in cli.list_instruments():
            instrument = cli.get_instrument('test')
        else:
            instrument = cli.create_instrument(
                'instrumentserver.testing.dummy_instruments.generic.DummyInstrumentRandomNumber',
                'test')


        self.parameters = []

        # read the config file
        parameters, refresh, save_directory = read_config('logger')


        # create the LoggerParameters based on the config file
        for params in parameters:
            self.parameters.append(LoggerParameters(name=params[0],
                                                    source_type=params[1],
                                                    parameter_path=params[2],
                                                    server=params[3],
                                                    port=params[4],
                                                    interval=params[5]))

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

    def save_data(self):
        """
        Saves the data in the specified file indicated in the config dictionary.
        Deletes the data from memory once it has been saved to storage.
        """
        # go through the parameters and create DataFrames with their data
        df_list = []
        for params in self.parameters:
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
        Main loop of the logger. Constantly running checking if its time to either save data or collect new data.
        """
        self.active = True

        while self.active:
            # checks what is the current time
            current_t = datetime.datetime.now()

            # check if its time to save data
            if (current_t - self.last_saved_t).total_seconds() >= self.refresh:
                self.save_data()
                self.last_saved_t = current_t

            # individually check if its time to collect data from each parameter
            for params in self.parameters:
                if (current_t - params.last_saved_t).total_seconds() >= params.interval:
                    params.update()
                    params.last_saved_t = current_t

        return
