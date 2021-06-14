import os
import pandas as pd
import itertools
from typing import Optional, List

from bokeh.layouts import column, row
from bokeh.models import ColumnDataSource, CheckboxGroup, DatetimeTickFormatter, HoverTool, DataRange1d
from bokeh.models.widgets import Button, Tabs, Panel, Paragraph
from bokeh.plotting import figure
from bokeh.palettes import Category10

from .startupconfig_draft import config


class PlotParameter:
    """
    PlotParameter is used to hold an individual parameter of the plot.
    It saves the data of it as well as draws the lines for the figures.

    :param name: The name of the parameter.

    """
    def __init__(self, name, color=None):
        self.name = name
        self.data = []
        self.time = []
        self.color = color
        self.source = ColumnDataSource(data={self.name: self.data, f'{self.name}_time': self.time})

    def create_line(self, fig: figure, color):
        """
        Creates the line in the specified figure based on the ColumnDataSource of this parameter.

        :param fig: bokeh figure object where this line is going to live.
        :param color: used to cycle through the colors.
        """
        return fig.line(x=f'{self.name}_time', y=self.name,
                        source=self.source, legend_label=self.name, color=color)

    def update(self, data, time):
        """
        Updates the data in the PlotParameter and updates the data in the ColumnDataSource.

        :param data: Data points loaded from the csv file
        :param time: Time points loaded from the csv file
        """

        # replace data from memory
        self.data = data
        self.time = time

        # create new dictionary
        new_data = {
            self.name: self.data,
            f'{self.name}_time': self.time
        }

        # replace old dictionary in the ColumnDataSource for the new one.
        self.source.data = new_data


class Plots:
    """
    Holds all the parameters that live inside this specific plot as well as all of the graphical elements for it.

    :param name: Name of the plot.
    :param plot_params: List of PlotParameter containing the parameters of this plot.
    :param param_names: List of the names of the parameters.
    :param load_directory: Directory of the csv file where the data is stored.
    """

    def __init__(self, name: str,
                 plot_params: List[PlotParameter],
                 param_names: List[str],
                 load_directory: str):
        # load values
        self.name = name
        self.plot_params = plot_params
        self.param_names = param_names
        self.load_directory = load_directory

        self.title = Paragraph(text=self.name, width=1000, height=200,
                               style={
                                   'font-size': '40pt',
                                   'font-weight': 'bold'
                               })

        # set up the tools and the figure itself
        self.tools = 'pan,wheel_zoom,box_zoom,reset,save'
        self.hover_tool = HoverTool(
            tooltips=[
                ('value', '$y'),
                ('time', '$x{%H:%M:%S}')
            ],
            formatters={
                '$x': 'datetime'
            },

            mode='mouse'
        )
        self.ticker_datetime = DatetimeTickFormatter(minsec=['%H:%M:%S %m/%d'])
        # iterator used to cycle through colors
        self.colors = self.colors_gen()

        # setting up the linear figure
        self.fig_linear = figure(width=1000, height=1000,
                                 tools=self.tools, x_axis_type='datetime')
        self.fig_linear.xaxis[0].formatter = self.ticker_datetime

        # setup the hover formatter
        self.fig_linear.add_tools(self.hover_tool)
        # automatically updates the range of the y-axis to center only visible lines
        self.fig_linear.y_range = DataRange1d(only_visible=True)

        # setting up the log figure
        self.fig_log = figure(width=1000, height=1000,
                              tools=self.tools,
                              x_axis_type='datetime', y_axis_type='log')
        self.fig_log.xaxis[0].formatter = self.ticker_datetime

        # setup the hover formatter
        self.fig_log.add_tools(self.hover_tool)
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
                             row(Tabs(tabs=panels)),
                             self.checkbox,
                             row(self.all_button, self.none_button))

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

    def update_parameters(self, load_data: pd.DataFrame):
        """
        Reads the source file and updates the parameters
        """

        for params in self.plot_params:
            reduced_data_frame = load_data[load_data['name'] == params.name]
            data = reduced_data_frame['value'].tolist()
            time = reduced_data_frame['time'].tolist()

            params.update(data, time)


class DashboardClass:
    """
    Class used to share information between different sessions of the dashboard.
    It can load the config file to read for different specifications and
    has the function that creates the bokeh documents.
    """

    def __init__(self):
        # set the default options
        self.multiple_plots = []
        self.refresh = 10
        self.ips = ['*']
        self.load_directory = os.path.join(os.getcwd(), 'dashboard_data.csv')

        # read the config dictionary to change the defaults
        self.load_config()

    def load_config(self):
        """
        Reads the config dictionary and load the values and structure of the dashboard
        """

        # read the config file
        for plot in config.keys():
            # load the options
            if plot == 'options':
                if 'refresh_rate' in config[plot]:
                    # default value 1000
                    self.refresh = config[plot]['refresh_rate']
                if 'allowed_ip' in config[plot]:
                    self.ips = config[plot]['allowed_ip']
                if 'load_and_save' in config[plot]:
                    self.load_directory = config[plot]['load_and_save']
                else:
                    if 'load_directory' in config[plot]:
                        self.load_directory = config[plot]['load_directory']
            else:
                # create the plot and parameter structure
                param_list = []
                name_list = []
                for params in config[plot]:
                    param_list.append(PlotParameter(name=params))
                    name_list.append(params)
                self.multiple_plots.append(Plots(name=plot,
                                                 plot_params=param_list,
                                                 param_names=name_list,
                                                 load_directory=self.load_directory))

    def dashboard(self, doc):
        """
        Creates the document that bokeh uses for every session.
        It also sets the necessary callbacks to update the dashboard and collect new data.
        """

        def update_plots():
            """
            Function that gets called periodically to update the plots.
            Reads the data file specified in the config dictionary and updates the plots

            The try statement is there to catch the error if the file does not yet exist.
            It is possible to launch the dashboard without launching the logger first.
            When this happen the dashboard will raise an exception since it cannot find the file.
            In this function the exception is caught and a pass statements is followed.
            """
            try:
                load_data = pd.read_csv(self.load_directory, parse_dates=['time'])
                for plot in plot_list:
                    plot.update_parameters(load_data)
            except FileNotFoundError as e:
                pass

        # replicate the Plots and PlotParameters for a specific session
        plot_list = []
        layout_row = []
        for plt in self.multiple_plots:
            param_list = []
            name_list = []
            for params in plt.plot_params:
                temp_param = PlotParameter(name=params.name)
                name_list.append(params.name)
                param_list.append(temp_param)
            plot_list.append(Plots(plt.name, param_list, name_list, self.load_directory))

            # add the callback and update initially
            doc.add_periodic_callback(update_plots, self.refresh * 1000)
            update_plots()
            layout_row.append(plot_list[-1].layout)

        # add that final layout to the bokeh document
        layout = row(layout_row)
        doc.add_root(layout)

