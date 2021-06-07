from instrumentserver.client import Client as InstrumentClient
from .startupconfig_draft import config


from bokeh.layouts import column, row
from bokeh.models import ColumnDataSource, CheckboxGroup, DatetimeTickFormatter, HoverTool, DataRange1d
from bokeh.models.widgets import Button
from bokeh.plotting import figure
from bokeh.palettes import Category10

from typing import Optional, List
import itertools

import datetime


# Global variables used to share information between sessions of the bokeh server.

# List[Plots]
# used only by the first bokeh session and every other one reads from that global variable
multiple_plots = []

# Boolean
# used to see if its the first time creating the plots
first = True

# int
# used to set the refresh rate for non-original sessions
refresh = 1000


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
                 server: Optional[str] = 'localhost',
                 port: Optional[int] = 5555,
                 interval: Optional[int] = 1000,
                 source: Optional[ColumnDataSource] = None):

        global first

        # load values
        self.name = name
        self.source_type = source_type
        self.parameter_path = parameter_path
        self.server = server
        self.port = port
        self.addr = f"tcp://{self.server}:{self.port}"
        self.interval = interval

        # check if there is any data to load. If there is load it, if not create an empty ColumnDataSource
        if source is None:
            self._data = []
            self._time = []
            self.source = ColumnDataSource(data={
                self.name : self._data,
                f'{self.name}_time' : self._time
            })
        else:
            self.source = ColumnDataSource(data=source.data)
            self._data = self.source.data[self.name]
            self._time = self.source.data[f'{self.name}_time']

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
                self._data.append(new_data)
                self._time.append(current_time)

                # create new dictionary with new values to stream to the ColumnDataSource object and updates it.
                new_data_dict = {
                    self.name: [new_data],
                    f'{self.name}_time': [current_time]
                }
                self.source.stream(new_data_dict)

            else:
                # update data
                self._data = data
                self._time = time

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

        # set up the tools and the figure itself
        self.tools = 'pan,wheel_zoom,box_zoom,reset,save'

        self.fig = figure(width=1000, height=1000,
                          tools=self.tools, title=self.name,
                          x_axis_type='datetime')
        self.fig.xaxis[0].formatter = DatetimeTickFormatter(minsec = ['%H:%M:%S'])

        # setup the hover formatter
        self.fig.add_tools(HoverTool(
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
        self.fig.y_range = DataRange1d(only_visible=True)

        # Create the checkbox and the buttons and their respective triggers
        self.checkbox = CheckboxGroup(labels=self.param_names, active=list(range(len(self.param_names))))
        self.all_button = Button(label='select all')
        self.none_button = Button(label='deselect all')

        self.checkbox.on_click(self.update_lines)
        self.all_button.on_click(self.all_selected)
        self.none_button.on_click(self.none_selected)

        # iterator used to cycle through colors
        colors = self.colors_gen()

        # creates the lines
        self.lines = []
        for params, c in zip(self.plot_params, colors):
            self.lines.append(params.create_line(fig=self.fig, color=c))

        # creates the layout with all of the elements of this plot GUI
        self.layout = column(self.fig, self.checkbox, row(self.all_button, self.none_button))

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
        for i in range(0, len(self.lines)):
            if i in active:
                self.lines[i].visible = True
            else:
                self.lines[i].visible = False

    def all_selected(self):
        """
        Sets all the lines to be visible. Gets called when the select all button is clicked
        """
        self.checkbox.active = list(range(len(self.lines)))
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
            params.update(params.source.data[params.name],  params.source.data[f'{params.name}_time'])

def load_dashboard():
    """
    Loads the information from the config file into the global variable multiple_plots to be used by the dashboard.
    """
    global multiple_plots

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

    def read_config(config) -> [List, List]:
        """
        Reads the config file and creates all the PlotParameters and saves them in their respective Plots.
        returns a list of the Plots, and a list of the allowed ip addresses.
        Through this all of the GUI elements are also created in the Plots constructor.

        :param config: The config dictionary located in the config file
        """
        global multiple_plots
        global refresh

        plot_list = []

        # default value
        ip_list = ['*']
        # goes through the config dictionary and constructs the classes
        for plot in config.keys():

            # check if the key is options and load the specified settings.
            if plot == 'options':
                if 'refresh_rate' in config[plot]:
                    # default value 1000
                    refresh = config[plot]['refresh_rate']
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
                                               interval=interval_param)
                    # adds the parameter and its name to lists to pass to the Plot constructor.
                    param_list.append(plt_param)
                    param_names.append(params)

                # creates the plots and appends them to a list.
                plt = Plots(name=plot,
                            plot_params=param_list,
                            param_names=param_names)

                plot_list.append(plt)
        return plot_list, ip_list
    # load the values in the global variable and return the list of ip addresses
    multiple_plots, ip_holder = read_config(config)
    return ip_holder



def dashboard(doc):
    """
    Creates the document that bokeh uses for every session.
    It also sets the necessary callbacks to update the dashboard and collect new data.
    """

    global multiple_plots
    global first
    global refresh

    # check if  this is the first time running the dashboard
    if first:

        first = False
        layout_row = []

        # go through each parameter and add the necessary callback
        # go through each plot and add the layout to the layout list
        for plt in multiple_plots:
            for params in plt.plot_params:
                if params.source_type == 'parameter':
                    doc.add_periodic_callback(params.update, params.interval)
            layout_row.append(plt.layout)

        # add the layouts to the document
        doc.add_root(row(layout_row))
    else:
        # if this is not the original session,
        # creates a copy of every object with all of their values for the new session
        plot_list = []
        layout_row = []
        for plt in multiple_plots:
            param_list = []
            name_list = []
            for params in plt.plot_params:
                temp_param = PlotParameters(name=params.name,
                                            source_type=params.source_type,
                                            parameter_path=params.parameter_path,
                                            server=params.server,
                                            port=params.port,
                                            interval=params.interval,
                                            source=params.source)
                name_list.append(params.name)
                param_list.append(temp_param)
            # set the update parameters callback with the refresh value and append the layout to the list
            plot_list.append(Plots(plt.name, param_list, name_list))
            doc.add_periodic_callback(plot_list[-1].update_parameters, refresh)
            layout_row.append(plot_list[-1].layout)

        # add that final layout to the bokeh document
        doc.add_root(row(layout_row))

