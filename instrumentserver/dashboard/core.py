from instrumentserver.client import Client as InstrumentClient
from .startupconfig_draft import config

from bokeh.io import curdoc
from bokeh.layouts import column, row
from bokeh.models.widgets import TextInput, Button, Paragraph
from bokeh.models import ColumnDataSource, DataRange1d, Select, CheckboxGroup
from bokeh.plotting import figure
from bokeh.palettes import Category10

from typing import Optional, List, Dict
import itertools
import numpy as np

# To run, write on command line in this directory:
# bokeh serve --show core.py

# This will bechanged to be its own class and start from a startup script with a proper command.

class PlotParameters:

    def __init__(self, name: str,
                 source_type: Optional[str] = None,
                 parameter_path: Optional[str] = None,
                 server: Optional[str] = 'localhost',
                 port: Optional[int] = 5555,
                 interval: Optional[int] = 10,
                 data: Optional[List[int]] = []):
        self.name = name
        self.source_type = source_type
        self.parameter_path = parameter_path
        self.server = server
        self.port = port
        self.addr = f"tcp://{self.server}:{self.port}"
        self.interval = interval
        self.data = data

    def __str__(self, indent=0):
        i = indent * ''
        ret = f"""name: {self.name}
{i}- source_type: {self.source_type}
{i}- parameter_path: {self.parameter_path}
{i}- addres: {self.addr}
{i}- interval: {self.interval}
{i}-data: {self.data}
"""
        return ret

class Plots:

    def __init__(self, name: str, plot_params: Optional[List[PlotParameters]] = []):
        self.name = name
        self.plot_params = plot_params

    def  __str__(self, indent=0):
        i = indent * ''
        ret = f"""name: {self.name}
{i}- plot_params: {self.plot_params}
"""
        return ret

def dashboard(doc):
    # Creating fake data
    x = np.linspace(-100, 100, 1000)
    y1 = x
    y2 = 0.1 * x**2
    y3 = 0.01 * x**3
    y4 = 1/x

    data = {
        'x': x,
        'linear': y1,
        'quadratic': y2,
        'cubed': y3,
        'hyperbolic': y4
    }
    keys = list(data.keys())

    #Getting data from the config file:
    def read_config(config):

        plot_list: List[Plots] = []

        for plot in config.keys():
            plt = Plots(plot)
            for params in config[plot].keys():
                plt_param = PlotParameters(name=params,
                                           source_type=config[plot][params]['source_type'],
                                           parameter_path=config[plot][params]['parameter_path'])
                if 'server' in config[plot][params]:
                    plt_param.server = config[plot][params]['server']
                if 'port' in config[plot][params]:
                    plt_param.port = config[plot][params]['port']
                if 'options' in config[plot][params]:
                    plt_param.interval = config[plot][params]['options']['interval']
                plt.plot_params.append(plt_param)

            plot_list.append(plt)
        return plot_list


    multiple_plots = read_config(config)

    # dealing with colors
    def color_gen():
        yield from itertools.cycle(Category10[10])

    colors = color_gen()

    # creating the objects
    data_checkbox = CheckboxGroup(labels=keys[1:], active=[0])

    all_button = Button(label='select all')
    none_button = Button(label='deselect all')

    source = ColumnDataSource(data=data)

    tools = 'pan,wheel_zoom,reset'

    main_fig = figure(width=1000, height=1000, tools=tools)

    lines = []
    for i, c in zip(range(1, len(keys)), colors):
        lines.append(main_fig.line(x=keys[0], y=keys[i], source=source, legend_label=f'{keys[i]}', color=c))

    def update(argument=None):
        active = data_checkbox.active

        for i in range(0, len(lines)):
            if i in active:
                lines[i].visible = True
            else:
                lines[i].visible = False

    def all_selected():
        data_checkbox.active = list(range(len(keys)))
        update()

    def none_selected():
        data_checkbox.active = []
        update()

    all_button.on_click(all_selected)
    none_button.on_click(none_selected)

    data_checkbox.on_click(update)
    update()

    layout = column(data_checkbox, row(all_button, none_button), main_fig)

    doc.add_root(layout)

