# -*- coding: utf-8 -*-

#%% imports
import inspect

import numpy as np
from qcodes import Station, Instrument
from qcodes.utils import validators

from instrumentserver import QtWidgets

from instrumentserver.gui import widgetDialog
from instrumentserver.params import ParameterManager
from instrumentserver.gui.instruments import ParameterManagerGui
from instrumentserver.client import Client, ProxyInstrument



#%% run the PM locally
Instrument.close_all()
pm = ParameterManager('pm')
station = Station()
station.add_component(pm)
dialog = widgetDialog(ParameterManagerGui(pm))


#%% instantiate PM in the server.
Instrument.close_all()

cli = Client()
pm2 = ProxyInstrument('pm', cli=cli, remotePath='pm')
dialog = widgetDialog(ParameterManagerGui(pm2))