from ..client import Client as InstrumentClient

from bokeh.io import curdoc
from bokeh.layouts import column, row
from bokeh.models.widgets import TextInput, Button, Paragraph
from bokeh.models import ColumnDataSource, DataRange1d, Select, CheckboxGroup
from bokeh.plotting import figure
from bokeh.palettes import Category10

import itertools
import numpy as np

# To run, write on command line in this directory:
# bokeh serve --show core.py

#This will bechanged to be its own class and start from a startup script with a proper command.


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




#dealing with colors
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
    global clicker
    clicker += 1
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

layout = column(data_checkbox, row(all_button, none_button), main_fig, counter_par)

curdoc().add_root(layout)

