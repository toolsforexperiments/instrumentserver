# -*- coding: utf-8 -*-
"""
Created on Wed Jun  3 11:50:08 2020

@author: Ryan
"""
#%% Setup
from instrumentserver import setupLogging, logger, QtWidgets, client, serialize
from instrumentserver.log import LogWidget
from instrumentserver.client import QtClient
from instrumentserver.client.application import InstrumentClientMainWindow
from instrumentserver.gui.instruments import ParameterManagerGui
from instrumentserver.client.proxy import Client
from qcodes import Instrument

#%%
runfile(r'C:\Users\Ryan\Documents\GitHub\instrumentserver\mockUp\hatlab_modules\startup.py')
# gets cli, VNA, CS, and PM

#%% Beginning the measurement and setting some default values

#setting instrument settings like IFBW in VNA or ramp_rate in a current source
# are handled in a virtual front panel? Or set here?

#create sweep parameters in the parameter manager
try: 
    pm.add_parameter('current_start', unit = 'mA', initial_value = 0)
    pm.add_parameter('current_stop', unit = 'mA', initial_value = 1)
    pm.add_parameter('current_steps', initial_value = 100)
except ValueError: 
    pass
#%% Writing
FN = './ddh5_test-2'
nrows = 100
DATADIR = "./data"

current_arr = np.linspace(pm.current_start(), pm.current_stop(), int(pm.current_steps()))

data = dd.DataDict(
    current = dict(unit='mA'),
    frequency = dict(unit='Hz'),
    s11 = dict(axes=['current', 'frequency']), # no unit, real magnitude
)
data.validate() # this is just for catching mistakes.

with dds.DDH5Writer(DATADIR, data, name='FluxSweep') as writer:
    for c in current_arr:
        resp = vna.get_trace()
        time.sleep(0.2)
        
        # the writer accepts one line for each data field.
        # that means we should reshape the data that each entry has the form [<data>].
        # for practical purposes that means that each frequency and s11 data array
        # is like one datapoint.
        writer.add_data(
            current = [c],
            frequency = vna.frequency().reshape(1,-1),
            s11 = vna.get_trace().reshape(1,-1),
        )
#%% Reading
# this is detecting the grid in the data
data_as_grid = dd.datadict_to_meshgrid(data)

flux_data = data_as_grid.data_vals('current')
frq_data = data_as_grid.data_vals('frequency')
s11_data = data_as_grid.data_vals('s11')

fig, ax = plt.subplots(1, 1)

ax.imshow(
    np.angle(s11_data.T), 
    aspect='auto', origin='lower',
    extent=[flux_data.min(), flux_data.max(), frq_data.min(), frq_data.max()]
)
ax.set_xlabel('Current(mA)')
ax.set_ylabel('Frequency (Hz)')



