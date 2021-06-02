"""

How to set up config file for the dashboard:
############################################

The file should consist solely of a dictionary called config.

This dictionary is a combination of multiple nested dictionaries.

this first field represts individual plots. There can be multiple of them. Each plot will have its key as a name for it.
inside each plot there should be a dictionary for every parameter that should be displayed inside that plot.
each parameter will have its name as a key and must have source_type and parameter_path, a few more options are available.

Source_type: only 2 options: 'parameter': this indicates that the dashboard needs to ask for values to the instrument_name
                                          server. If parameter is selected, interval should be specified but not necesary
                                          the default value is 1000. the interval is in ms
                            'broadcast': not implemented yet. Would pick up values from the automatic broadcast of parameter
                                         changes from the instrumentserver. If broadcast is selectted, in options, actions
                                         should specify which updates to listen for. Default behaviour: all of them.

parameter_path: the string of the speicifcied parameter with all of the submodules in.
                The first submodule should always be the name of the instrument_name. Ex:'parameters.qubit.pipulse.len'
                                                                                    'triton.T1'

server: the location of the server.

port: the port

data can be presented in the filed data

update is only working with drivers that have .get('parameter_name')

current global data updates happens at the lowest interval given. This only applies to visual changes and not data gathering

"""