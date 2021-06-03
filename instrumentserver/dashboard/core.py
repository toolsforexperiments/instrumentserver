from instrumentserver.client import Client as InstrumentClient
from .startupconfig_draft import config


from bokeh.layouts import column, row
from bokeh.models.widgets import Button
from bokeh.models import ColumnDataSource, CheckboxGroup, DatetimeTickFormatter, HoverTool
from bokeh.plotting import figure
from bokeh.palettes import Category10

from typing import Optional, List
import itertools

import datetime

class PlotParameters:

    def __init__(self, name: str,
                 source_type: str,
                 parameter_path: str,
                 server: Optional[str] = 'localhost',
                 port: Optional[int] = 5555,
                 interval: Optional[int] = 1000):
        self.name = name
        self.source_type = source_type
        self.parameter_path = parameter_path
        self.server = server
        self.port = port
        self.addr = f"tcp://{self.server}:{self.port}"
        self.interval = interval
        self._data = []
        self._time = []
        self._source = ColumnDataSource(data={
            self.name : self._data,
            f'{self.name}_time' : self._time
        })

        submodules = parameter_path.split('.')

        self.instrument_name = submodules[0]
        self.client = InstrumentClient(self.server, self.port)
        self.instrument = self.client.get_instrument(self.instrument_name)

        # get the name of the parameter with submodules
        parameter_name = ''
        for i in range(1, len(submodules)):
            parameter_name = parameter_name + submodules[i]
        self.parameter_name = parameter_name

    # This currently only works for the fridge. Need to think of a way of generalizing this
    def update(self):
        new_data = self.instrument.get(self.parameter_name)
        current_time = datetime.datetime.now()
        self._data.append(new_data)
        self._time.append(current_time)
        new_data_dict = {
            self.name : [new_data],
            f'{self.name}_time' : [current_time]
        }
        self._source.stream(new_data_dict)

        print(f'the time is: {current_time}. the new data is: {new_data}')

    def load_new_data(self):
        data = {
            self.name : self._temporary_data,
            f'{self.name}_time' : self._temporary_time
        }
        return data

    def get_data(self):
        return self._data

    def get_time(self):
        return self._time

    def create_line(self, fig: figure, color):
        return fig.line(x=f'{self.name}_time', y=self.name,
                              source=self._source, legend_label=self.name, color=color)



class Plots:

    def __init__(self, name: str,
                 plot_params: List[PlotParameters],
                 data_source: ColumnDataSource,
                 param_names: List[str]):
        self.name = name
        self.plot_params = plot_params
        self.data_source = data_source

        self.tools = 'pan,wheel_zoom,box_zoom,reset,save'

        self.fig = figure(width=1000, height=1000,
                          tools=self.tools, title=self.name,
                          x_axis_type='datetime')

        self.fig.add_tools(HoverTool(
            tooltips = [
                ('value', '$y'),
                ('time', '$x{%H:%M:%S}')
            ],
            formatters = {
                '$x': 'datetime'
            },

            mode='mouse'
        ))
        self.fig.xaxis[0].formatter = DatetimeTickFormatter(minsec = ['%H:%M:%S'])

        self.checkbox = CheckboxGroup(labels=param_names, active=list(range(len(param_names))))

        self.all_button = Button(label='select all')
        self.none_button = Button(label='deselect all')

        colors = self.colors_gen()

        self.lines = []
        for params, c in zip(self.plot_params, colors):
            self.lines.append(params.create_line(fig=self.fig,color=c))

        self.checkbox.on_click(self.update_lines)
        self.all_button.on_click(self.all_selected_plot)
        self.none_button.on_click(self.none_selected_plot)

        self.layout = column(self.fig, self.checkbox, row(self.all_button, self.none_button))

    def get_instruments(self):
        instruments = []
        for params in self.plot_params:
            if params.instrument_name not in instruments:
                instruments.append(params.instrument_name)
        return instruments

    def get_interval(self):
        interval = None
        for params in self.plot_params:
            if interval is None:
                interval = params.interval
            else:
                if params.interval < interval:
                    interval = params.interval
        return interval

    def update_data(self):
        data = {}
        for params in self.plot_params:
            params.update()
            appending_data = {params.name: params.get_data(),
                              f'{params.name}_time': params.get_time()}
            data.update(appending_data)
        self.data_source.data = data

    def colors_gen(self):
        yield from itertools.cycle(Category10[10])

    def update_lines(self, argument=None):
        active = self.checkbox.active

        for i in range(0, len(self.lines)):
            if i in active:
                self.lines[i].visible = True
            else:
                self.lines[i].visible = False

    def all_selected_plot(self):
        self.checkbox.active = list(range(len(self.lines)))
        self.update_lines()

    def none_selected_plot(self):
        self.checkbox.active = []
        self.update_lines()


def dashboard(doc):

    # Getting data from the config file:
    def read_config(config):

        plot_list: List[Plots] = []

        for plot in config.keys():
            param_list = []
            data_source = ColumnDataSource(data={})
            param_names = []
            for params in config[plot].keys():
                # default configs. If they exist in config they will get overwritten. Used for constructor.
                server_param = 'localhost'
                port_param = 5555
                interval_param = 1000

                if 'server' in config[plot][params]:
                    server_param = config[plot][params]['server']
                if 'port' in config[plot][params]:
                    port_param = config[plot][params]['port']
                if 'options' in config[plot][params]:
                    if 'interval' in config[plot][params]['options']:
                        interval_param = config[plot][params]['options']['interval']

                plt_param = PlotParameters(name=params,
                                           source_type=config[plot][params]['source_type'],
                                           parameter_path=config[plot][params]['parameter_path'],
                                           server=server_param,
                                           port=port_param,
                                           interval=interval_param)

                param_list.append(plt_param)
                param_names.append(params)
                data_source.data[params] = []
                data_source.data[f'{params}_time'] = []

            plt = Plots(name=plot, plot_params=param_list, data_source=data_source, param_names=param_names)

            plot_list.append(plt)
        return plot_list

    def callback_setup(plot_list, doc) -> None:
        for plt in plot_list:
            for params in plt.plot_params:
                if params.source_type == 'parameter':
                    print(f'the param is: {params}, the interval is: {params.interval}')
                    doc.add_periodic_callback(params.update, params.interval)

    # Starting the setup
    multiple_plots = read_config(config)
    callback_setup(multiple_plots, doc)

    layout_row = []
    for plt in multiple_plots:
        layout_row.append(plt.layout)

    doc.add_root(row(layout_row))

