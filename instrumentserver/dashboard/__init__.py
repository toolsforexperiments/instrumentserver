"""
==========
Dashboard:
==========

The dashboard consists of a bokeh server that displays real time updates of speicified parameters.
The dashboard can be configured by a dictionary in the startupconfig file located inside the dashboard package.

How to set up config file for the dashboard:
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The file should consist solely of a dictionary called config.
This dictionary is a combination of multiple nested dictionaries.

This first field represents individual plots. There can be multiple of them. Each plot will have its key as a name for it.
Inside each plot there should be a dictionary for every parameter that should be displayed inside that specific plot.
Each parameter will have its name as a key and must have source_type and parameter_path, a few more options are available.

update is only working with drivers that have the method .get('parameter_name') and returns the int value asked.

Source_type:
    only 2 options:
        'parameter':
            this indicates that the dashboard needs to ask for values to the instrument_name
            server. If parameter is selected, interval should be specified but not necesary
            the default value is 1000. the interval is in ms
        'broadcast':
            NOT IMPLEMENTED. Would pick up values from the automatic broadcast of parameter
            changes from the instrumentserver. If broadcast is selectted, in options, actions
            should specify which updates to listen for. Default behaviour: all of them.

parameter_path:
    The string of the speicifcied parameter with all of the submodules in.
    The first submodule should always be the name of the instrument_name. Ex:'parameters.qubit.pipulse.len'
    'triton.T1'

server:
    The location of the instrumentserver.

port:
    The port of the instrument server


Example:
^^^^^^^^

The following is an example dictionary::

    config = {
        'Fridge temps 1' : {
            'PT2 Head': {
                'source_type': 'parameter',
                'parameter_path': 'triton.T1',
                'server': 'localhost',
                'port': 5555,
                'options': {
                    'interval': 5000
                },
            },

            'PT2 Plate': {
                'source_type': 'parameter',
                'parameter_path': 'triton.T2',
                'server': 'localhost',
                'port': 5555,
                'options': {
                    'interval': 1000
                },
            },
        },

        'Fridge temps 2': {
            'MC Plate RuO2': {
                'source_type': 'parameter',
                'parameter_path': 'triton.T8',
                'server': 'localhost',
                'port': 5555,
                'options': {
                    'interval': 500
                },
            },
        }
    }

This dictionary would be creating 2 different plot: 'Fridge temps 1' and 'Fridge temps 2'.
Fridge temps 1
    This plot has 2 different parameters: 'PT2 Head' and 'PT2 Plate'.
    PT2 Head
        This parameter has a type 'parameter',
        meaning that the dashboard will be asking the instrumentserver for updates.
        It will look for updates for T1 inside the object triton in the instrumentserver located at localhost:5555
        this will happen every 5000 ms or 5 seconds
    PT2 Plate
        This parameter has a type 'parameter',
        meaning that the dashboard will be asking the instrumentserver for updates.
        It will look for updates for T2 inside the object triton in the instrumentserver located at localhost:5555
        this will happen every 1000 ms or 1 second

Fridge temps 2
    This plot has a single parameter: 'MC Plate RuO2'
    MC Plate RuO2
        This parameter has a type 'parameter',
        meaning that the dashboard will be asking the instrumentserver for updates.
        It will look for updates for T8 inside the object triton in the instrumentserver located at localhost:5555
        this will happen every 500 ms or 0.5 seconds


"""