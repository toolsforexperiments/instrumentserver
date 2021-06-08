from ..client import Client as InstrumentClient
from .startupconfig_draft import config

from bokeh.layouts import column, row
from bokeh.models import ColumnDataSource, CheckboxGroup, DatetimeTickFormatter, HoverTool, DataRange1d,\
                         RadioButtonGroup
from bokeh.models.widgets import Button, Tabs, Panel, Paragraph, FileInput
from bokeh.plotting import figure
from bokeh.palettes import Category10

from typing import Optional, List

import os
import pandas as pd
import itertools
import datetime



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
                 first: bool,
                 server: Optional[str] = 'localhost',
                 port: Optional[int] = 5555,
                 interval: Optional[int] = 1000,
                 source: Optional[ColumnDataSource] = None):

        # load values
        self.name = name
        self.source_type = source_type
        self.parameter_path = parameter_path
        self.server = server
        self.port = port
        self.address = f"tcp://{self.server}:{self.port}"
        self.interval = interval

        # check if there is any data to load. If there is load it, if not create an empty ColumnDataSource
        if source is None:
            self.data = []
            self.time = []
            self.source = ColumnDataSource(data={
                self.name: self.data,
                f'{self.name}_time': self.time
            })
        else:
            self.source = ColumnDataSource(data=source.data)
            self.data = self.source.data[self.name]
            self.time = self.source.data[f'{self.name}_time']

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

        # check if this is an original parameter
        if first:
            self.original = True
        else:
            self.original = False

    def update(self, data=None, time=None):
        """
        This method has 2 purposes. If it is being called by an original parameter it gathers new data.
        if it is called by a non-original parameter, it updates its data with the parameters data and time.

        :param data: all of the data from the original parameter
        :param time: all of the time data from the original parameter
        """

        # check that the source type is parameter
        if self.source_type == 'parameter':
            if self.original:
                # gather new data and save it inside the class
                new_data = self.instrument.get(self.parameter_name)
                current_time = datetime.datetime.now()
                self.data.append(new_data)
                self.time.append(current_time)

                # create new dictionary with new values to stream to the ColumnDataSource object and updates it.
                new_data_dict = {
                    self.name: [new_data],
                    f'{self.name}_time': [current_time]
                }
                self.source.stream(new_data_dict)
            else:
                # update data
                self.data = data
                self.time = time

                # create new dictionary with new data
                data_dict = {
                    self.name: data,
                    f'{self.name}_time': time
                }

                # replace all data with the new data
                self.source.data = data_dict

        if self.source_type == 'broadcast':
            raise NotImplementedError

    def create_line(self, fig: figure, color):
        """
        Creates the line in the specified figure based on the ColumnDataSource of this parameter.

        :param fig: bokeh figure object where this line is going to live.
        :param color: used to cycle through the colors.
        """
        return fig.line(x=f'{self.name}_time', y=self.name,
                        source=self.source, legend_label=self.name, color=color)

    def update_from_data(self, data, time):
        """
        Only used to load data into the parameter.
        It receives new data, adds it to the data and time variable and updates
        """
        self.data.extend(data)
        self.time.extend(time)
        self.update(self.data, self.time)


class Plots:
    """
    Holds all the parameters that live inside this specific plot as well as all of the graphical elements for it.

    :param name: Name of the plot.
    :param plot_params: List of PlotParameters containing the parameters of this plot.
    :param param_names: List of the names of the parameters.
    """

    def __init__(self, name: str,
                 plot_params: List[PlotParameters],
                 param_names: List[str]):
        # load values
        self.name = name
        self.plot_params = plot_params
        self.param_names = param_names

        self.title = Paragraph(text=self.name, width=1000, height=200,
                               style={
                                   'font-size': '40pt',
                                   'font-weight': 'bold'
                               })

        # set up the tools and the figure itself
        self.tools = 'pan,wheel_zoom,box_zoom,reset,save'
        # iterator used to cycle through colors
        self.colors = self.colors_gen()

        # setting up the linear figure
        self.fig_linear = figure(width=1000, height=1000,
                                 tools=self.tools, x_axis_type='datetime')
        self.fig_linear.xaxis[0].formatter = DatetimeTickFormatter(minsec=['%H:%M:%S %m/%d'])

        # setup the hover formatter
        self.fig_linear.add_tools(HoverTool(
            tooltips=[
                ('value', '$y'),
                ('time', '$x{%H:%M:%S}')
            ],
            formatters={
                '$x': 'datetime'
            },

            mode='mouse'
        ))
        # automatically updates the range of the y-axis to center only visible lines
        self.fig_linear.y_range = DataRange1d(only_visible=True)

        # setting up the log figure
        self.fig_log = figure(width=1000, height=1000,
                              tools=self.tools,
                              x_axis_type='datetime', y_axis_type='log')
        self.fig_log.xaxis[0].formatter = DatetimeTickFormatter(minsec=[f'%H:%M:%S %m/%d'])

        # setup the hover formatter
        self.fig_log.add_tools(HoverTool(
            tooltips=[
                ('value', '$y'),
                ('time', '$x{%H:%M:%S}')
            ],
            formatters={
                '$x': 'datetime'
            },

            mode='mouse'
        ))
        # automatically updates the range of the y-axis to center only visible lines
        self.fig_log.y_range = DataRange1d(only_visible=True)

        # creates the lines
        self.lines_linear = []
        self.lines_log = []
        for params, c in zip(self.plot_params, self.colors):
            self.lines_linear.append(params.create_line(fig=self.fig_linear, color=c))
            self.lines_log.append(params.create_line(fig=self.fig_log, color=c))

        # Create the checkbox and the buttons and their respective triggers
        self.checkbox = CheckboxGroup(labels=self.param_names, active=list(range(len(self.param_names))))
        self.all_button = Button(label='select all')
        self.none_button = Button(label='deselect all')

        self.checkbox.on_click(self.update_lines)
        self.all_button.on_click(self.all_selected)
        self.none_button.on_click(self.none_selected)

        # create the panels to switch from linear to log
        panels = [Panel(child=self.fig_linear, title='linear'), Panel(child=self.fig_log, title='log')]

        # creates the layout with all of the elements of this plot GUI
        self.layout = column(self.title,
                             Tabs(tabs=panels),
                             self.checkbox,
                             row(self.all_button, self.none_button))

    def get_instruments(self) -> List:
        """
        Returns a list of the instruments of the parameters in the plot.
        """
        instruments = []
        for params in self.plot_params:
            if params.instrument_name not in instruments:
                instruments.append(params.instrument_name)
        return instruments

    def colors_gen(self):
        """
        Iterator used to cycle through colors
        """
        yield from itertools.cycle(Category10[10])

    def update_lines(self, active: List[int]):
        """
        Updates which line is visible. gets called everytime either a button gets click or a checkbox gets clicked.

        :param active: List indicating what lines are visible.
        """
        # set each line to be visible or invisible depending on the checkboxes
        for i in range(0, len(self.lines_linear)):
            if i in active:
                self.lines_linear[i].visible = True
                self.lines_log[i].visible = True
            else:
                self.lines_linear[i].visible = False
                self.lines_log[i].visible = False

    def all_selected(self):
        """
        Sets all the lines to be visible. Gets called when the select all button is clicked
        """
        self.checkbox.active = list(range(len(self.lines_linear)))
        self.update_lines(self.checkbox.active)

    def none_selected(self):
        """
        Sets all the lines to be invisible. Gets called when the select none button is clicked
        """
        self.checkbox.active = []
        self.update_lines(self.checkbox.active)

    def update_parameters(self):
        """
        Used to update non-original sessions of the bokeh server
        """
        for params in self.plot_params:
            params.update(params.source.data[params.name], params.source.data[f'{params.name}_time'])


class DashboardClass:
    """
    This class holds all of the information about the dashboard. It is primarily used to share data between different
    sessions of the bokeh server.

    :param multiple_plots: List of all of the Plots objects in the dashboard.
                           These Plots objects hold PlotParameter where the data is stored
    :param first: Flag to see if the this is the first running instance
    :param refresh: Time interval in which different sessions refresh the dashboard (different from data gathering)
    """

    def __init__(self):
        self.multiple_plots = []
        self.first = True
        self.refresh = 1000

    def save_data(self):
        """
        Saves all the data in the dashboard in a csv file of the name dashboard_data.csv.
        The data is stored from the directory that the dashboard has been run in the command line.
        """

        plot_data_frame = []
        for plt in self.multiple_plots:
            params_data_frame = []
            for params in plt.plot_params:
                holder_data_frame = pd.DataFrame({'time': params.time,
                                                  'value': params.data,
                                                  'name': params.name,
                                                  'parameter_path': params.parameter_path,
                                                  'address': params.address,
                                                  'plot': plt.name
                                                  })
                params_data_frame.append(holder_data_frame)
            plot_data_frame.append(pd.concat(params_data_frame, ignore_index=True))
        ret_data_frame = pd.concat(plot_data_frame, ignore_index=True)
        ret_data_frame.to_csv(os.path.join(os.getcwd(), 'dashboard_data.csv'))

    def load_data(self):
        """
        Loads data from a csv file called dashboard_data.csv into the dashboard.
        It will look for the file in the directory that the dashboard has been run in the command line.
        """
        load_data = pd.read_csv(os.path.join(os.getcwd(), 'dashboard_data.csv'))
        for plt in self.multiple_plots:
            for params in plt.plot_params:
                reduced_data_frame = load_data[load_data['name'] == params.name]
                data = reduced_data_frame['value'].tolist()
                time = reduced_data_frame['time'].tolist()

                params.update_from_data(data, time)

    def load_dashboard(self):
        """
        Loads the information from the config file into multiple_plots to be used by the dashboard.
        Returns the list of valid ips
        """

        # used for testing, the instruments should be already created for the dashboard to work
        cli = InstrumentClient()

        if 'triton' in cli.list_instruments():
            fridge = cli.get_instrument('triton')
        else:
            fridge = cli.create_instrument(
                'qcodes.instrument_drivers.oxford.triton.Triton',
                'triton',
                address='128.174.249.18',
                port=33576)

        plot_list = []

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

            else:
                param_list = []
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
                                               first=self.first)
                    # adds the parameter and its name to lists to pass to the Plot constructor.
                    param_list.append(plt_param)
                    param_names.append(params)

                # creates the plots and appends them to a list.
                plt = Plots(name=plot,
                            plot_params=param_list,
                            param_names=param_names)

                plot_list.append(plt)
        # load the values in the global variable and return the list of ip addresses
        self.multiple_plots = plot_list
        return ip_list

    def dashboard(self, doc):
        """
        Creates the document that bokeh uses for every session.
        It also sets the necessary callbacks to update the dashboard and collect new data.
        """

        save_button = Button(label='Save data')
        load_button = Button(label='Load data')

        save_button.on_click(self.save_data)
        load_button.on_click(self.load_data)

        # check if  this is the first time running the dashboard
        if self.first:

            self.first = False
            layout_row = []

            # go through each parameter and add the necessary callback
            # go through each plot and add the layout to the layout list
            for plt in self.multiple_plots:
                for params in plt.plot_params:
                    if params.source_type == 'parameter':
                        doc.add_periodic_callback(params.update, params.interval)
                layout_row.append(plt.layout)

            # add the layouts to the document
            layout = column(row(layout_row), row(save_button, load_button))
            doc.add_root(layout)
        else:
            # if this is not the original session,
            # creates a copy of every object with all of their values for the new session
            plot_list = []
            layout_row = []
            for plt in self.multiple_plots:
                param_list = []
                name_list = []
                for params in plt.plot_params:
                    temp_param = PlotParameters(name=params.name,
                                                source_type=params.source_type,
                                                parameter_path=params.parameter_path,
                                                server=params.server,
                                                port=params.port,
                                                interval=params.interval,
                                                source=params.source,
                                                first=self.first)
                    name_list.append(params.name)
                    param_list.append(temp_param)
                # set the update parameters callback with the refresh value and append the layout to the list
                plot_list.append(Plots(plt.name, param_list, name_list))
                doc.add_periodic_callback(plot_list[-1].update_parameters, self.refresh)
                layout_row.append(plot_list[-1].layout)

            # add that final layout to the bokeh document
            layout = column(row(layout_row), row(save_button, load_button))
            doc.add_root(layout)

