import datetime
import os
from typing import Optional, List

from bokeh.models import ColumnDataSource
import pandas as pd

from ..client import Client as InstrumentClient
from .startupconfig_draft import config



class PlotParameters:
    """
    Class that holds and individual parameter of the dashboard. It lives inside a Plots class.

    :param name: Name of the parameter.
    :param source_type: Specifies how to gather the data for the parameter (parameter or broadcast).
    :param parameter_path: Full name with submodules of the qcodes parameter.
    :param server: Location of the server, defaults to 'localhost'.
    :param port: Defaults to 5555.
    :param interval: Interval of time to gather new updates in ms,
                     only impactful if source_type is of the parameter type. defaults to 1000.
    :param source: ColumnDataSource object with the data that should be loaded in the parameter. Defaults to None.
    """

    def __init__(self, name: str,
                 source_type: str,
                 parameter_path: str,
                 plot: str,
                 server: Optional[str] = 'localhost',
                 port: Optional[int] = 5555,
                 interval: Optional[int] = 1000):

        # load values
        self.name = name
        self.source_type = source_type
        self.parameter_path = parameter_path
        self.server = server
        self.port = port
        self.address = f"tcp://{self.server}:{self.port}"
        self.interval = interval
        self.plot = plot

        # check if there is any data to load. If there is load it, if not create an empty ColumnDataSource

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

        self.color = None
        self.last_saved_t = datetime.datetime.now()

    def update(self, data=None, time=None):
        """
        This method has 2 purposes. If it is being called by an original parameter it gathers new data.
        if it is called by a non-original parameter, it updates its data with the parameters data and time.

        :param data: all of the data from the original parameter
        :param time: all of the time data from the original parameter
        """

        # check that the source type is parameter
        if self.source_type == 'parameter':

            # just for development
            self.instrument.generate_data(self.parameter_name)

            # gather new data and save it inside the class
            new_data = self.instrument.get(self.parameter_name)
            current_time = datetime.datetime.now()
            self.data.append(new_data)
            self.time.append(current_time)

        if self.source_type == 'broadcast':
            raise NotImplementedError

class ServerLogger:

    def __init__(self):
        self.parameters = []
        self.plots = {}
        self.first = True
        self.refresh = 10
        self.save_directory = os.path.join(os.getcwd(), 'dashboard_data.csv')
        self.load_directory = os.path.join(os.getcwd(), 'dashboard_data.csv')
        self.active = False
        self.last_saved_t = datetime.datetime.now()

    def read_config(self):
        """
        Loads the information from the config file into multiple_plots to be used by the dashboard.
        Returns the list of valid ips
        """

        # used for testing, the instruments should be already created for the dashboard to work
        cli = InstrumentClient()

        if 'test' in cli.list_instruments():
            instrument = cli.get_instrument('test')
        else:
            instrument = cli.create_instrument(
                'instrumentserver.testing.dummy_instruments.generic.DummyInstrumentRandomNumber',
                'test')

        # default value
        ip_list = ['*']
        # goes through the config dictionary and constructs the classes
        for plot in config.keys():

            # check if the key is options and load the specified settings.
            if plot == 'options':
                if 'refresh_rate' in config[plot]:
                    # default value 1000
                    self.refresh = config[plot]['refresh_rate']
                if 'allowed_ip' in config[plot]:
                    ip_list = config[plot]['allowed_ip']
                if 'load_and_save' in config[plot]:
                    self.load_directory = config[plot]['load_and_save']
                    self.save_directory = config[plot]['load_and_save']
                else:
                    if 'save_directory' in config[plot]:
                        self.save_directory = config[plot]['save_directory']
                    if 'load_directory' in config[plot]:
                        self.load_directory = config[plot]['load_directory']
            else:

                param_names = []
                for params in config[plot].keys():

                    # default configs. If they exist in config they will get overwritten. Used for constructor.
                    server_param = 'localhost'
                    port_param = 5555
                    interval_param = 1000

                    # check if the optional options exist in the dictionary and overwrites them if they do.
                    if 'server' in config[plot][params]:
                        server_param = config[plot][params]['server']
                    if 'port' in config[plot][params]:
                        port_param = config[plot][params]['port']
                    if 'options' in config[plot][params]:
                        if 'interval' in config[plot][params]['options']:
                            interval_param = config[plot][params]['options']['interval']

                    # creates the PlotParameter object with the specified parameters
                    plt_param = PlotParameters(name=params,
                                               source_type=config[plot][params]['source_type'],
                                               parameter_path=config[plot][params]['parameter_path'],
                                               server=server_param,
                                               port=port_param,
                                               interval=interval_param,
                                               plot=plot)
                    # adds the parameter and its name to lists to pass to the Plot constructor.
                    self.parameters.append(plt_param)
                    param_names.append(params)

                self.plots[plot] = param_names

        return ip_list

    def save_data(self):

        df_list = []
        for params in self.parameters:
            holder_df = pd.DataFrame({'time': params.time,
                                      'value': params.data,
                                      'name': params.name,
                                      'parameter_path': params.parameter_path,
                                      'address': params.address
                                      })
            df_list.append(holder_df)
        ret = pd.concat(df_list, ignore_index=True)
        ret.to_csv(self.save_directory, index=False, mode='a')

    def dashboard_config(self):
        """
        Returns all of the configurations the dashboard needs.
        first the refresh time and then the plot structure.
        """

        return self.refresh, self.plots

    def run_logger(self):

        self.active = True

        while self.active:
            current_t = datetime.datetime.now()
            if (current_t - self.last_saved_t).total_seconds() >= self.refresh:
                self.save_data()
                self.last_saved_t = current_t

            for params in self.parameters:
                if (current_t - params.last_saved_t).total_seconds() >= params.interval:
                    params.update()
                    params.last_saved_t = current_t

