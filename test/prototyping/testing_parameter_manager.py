# -*- coding: utf-8 -*-

# %% imports

from qcodes import Instrument, Station

from instrumentserver.client import Client, ProxyInstrument
from instrumentserver.gui import widgetDialog
from instrumentserver.gui.instruments import ParameterManagerGui
from instrumentserver.params import ParameterManager

# %% run the PM locally
Instrument.close_all()
pm = ParameterManager("pm")
station = Station()
station.add_component(pm)
dialog = widgetDialog(ParameterManagerGui(pm))


# %% instantiate PM in the server.
Instrument.close_all()

cli = Client()
pm2 = ProxyInstrument("pm", cli=cli, remotePath="pm")
dialog = widgetDialog(ParameterManagerGui(pm2))
