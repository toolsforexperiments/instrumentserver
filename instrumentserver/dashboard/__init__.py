"""
=====================
Dashboard and Logger:
=====================

The dashboard package has 2 different programs in it, a parameter logger and a web dashboard to display that logging.
They both share a single config file from which it reads different settings and which parameters to log.
The logger is constantly writing in a csv file the values of the specified parameters while the dashboard reads the csv
file and displays the information.

The dashboard is capable of creating multiple plots side by side and displaying the specified parameters inside of it.
This can be used to display separately different categories of parameters like temperature in one,
and pressure in another one.

Both programs can be run simultaneously using the command 'dashboardlogger' or
separately using the command 'parameterlogger' and 'dashboard' in the command line. It is important to remember that
for the logger to work, the instrumentserver should already be running with the instruments already created.

The csv file has 5 different columns:
    time: The time in which this data point has been logged.

    value: The value of the parameter.

    name: The name of the parameter.

    parameter_path: Full name of the parameter, including all of its submodules, as it appears on the instrument driver.

    address: The address of the instrumentserver where the instrument of this parameters lives.

How to set up config file:
^^^^^^^^^^^^^^^^^^^^^^^^^^

The file should be located in the dashboard folder inside of the instrumentserver package and should be called:
'config.py'. The file should have a python dictionary named config, this is the dictionary that is being read.
This dictionary is composed of multiple nested dictionaries.

This first field represents individual plots (with the one exception for the options dictionary).
There can be multiple of them, each representing an individual plot,
and they will be displayed in a row. Each plot will have its key as a name for it.
Inside each plot there should be a dictionary for every parameter that should be displayed inside that specific plot.
Each parameter will have its name as a key and must have a source_type and parameter_path.
A few more options for parameters are available.

Source_type:
    only 2 options:
        'parameter':
            This indicates that the logger needs to ask for values to the instrumentserver.
            If parameter is selected, interval should be specified in a separate options dictionary inside
            the parameter dictionary (see example below) but is not necessary.
            the default value is 1. the interval is in seconds.
        'broadcast':
            NOT IMPLEMENTED. Would pick up values from the automatic broadcast of parameter
            changes from the instrumentserver. If broadcast is selected, in options, actions
            should specify which updates to listen for. Default behaviour: all of them.

parameter_path:
    The string of the specified parameter with all of the submodules in.
    The first submodule should always be the name of the instrument. Ex:'parameters.qubit.pipulse.len' ,
    'triton.T1'

server:
    The location of the instrumentserver.

port:
    The port of the instrument server

The options dictionary at the same level of the plot are where the settings for both the logger and the dashboard
are located:

    options:
        This should be a dictionary at the same level of the plots in the dashboard.
            refresh_rate
                [int] This is both the amount of time, in seconds, between each time the logger saves data into the csv
                and the dashboard reads the csv to show updates.
                While the logger does record data for each individual parameter at its specified interval, it saves data
                into storage all at once at this refresh_rate interval.
            allowed_ip
                [List[str]] List of the allowed ips that the server will show the dashboard
                if ['*'], all ips are allowed and the server will show the dashboard to any browser that request it.
            save_directory
                [str] Directory of where the logger will save data. This should end with <name_of_file>.csv
            load_directory
                [str] Directory of where the dashboard will load data. This should end with <name_of_file>.csv
            load_and_save
                [str] Directory of where the dashboard will load and the logger save data.
                If this option is present, the dashboard will override save_directory and load_directory options.
                This should end with <name_of_file>.csv

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
                    'interval': 5
                },
            },

            'PT2 Plate': {
                'source_type': 'parameter',
                'parameter_path': 'triton.T2',
                'server': 'localhost',
                'port': 5555,
                'options': {
                    'interval': 1
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
                    'interval': 3
                },
            },
        },

        'options': {
            'refresh_rate': 30,
            'allowed_ip': ['*'],
            'load_and_save': 'C:/Users/Msmt/Documents/dashboard_data.csv'
        }
    }

This dictionary would be creating 2 different plots in the dashboard: 'Fridge temps 1' and 'Fridge temps 2'.

Fridge temps 1
    This plot has 2 different parameters: 'PT2 Head' and 'PT2 Plate'.

    PT2 Head
        This parameter has a type 'parameter',
        meaning that the logger will be asking the instrumentserver for updates.
        It will look for updates for T1 inside the object triton in the instrumentserver located at localhost:5555
        this will happen every 5 seconds.
    PT2 Plate
        This parameter has a type 'parameter',
        meaning that the logger will be asking the instrumentserver for updates.
        It will look for updates for T2 inside the object triton in the instrumentserver located at localhost:5555
        this will happen every 1 second.

Fridge temps 2
    This plot has a single parameter: 'MC Plate RuO2'
        MC Plate RuO2
            This parameter has a type 'parameter',
            meaning that the logger will be asking the instrumentserver for updates.
            It will look for updates for T8 inside the object triton in the instrumentserver located at localhost:5555
            this will happen every 3 seconds.

options
    These are the options for the logger and dashboard.
        refresh_rate
            How often the logger will save its data into storage and how often the dashboard will read the csv file
            for updates. This will happen every 30 seconds.
        allowed_ip
            List of allowed ip_addresses and ports that are allowed to see the website for the server.
            For ['*'] all addresses are allowed.
        load_and_save
            When this option is present both the logger and dashboard will be looking for the same file in the
            same directory. In this case the logger will be creating a file called 'dashboard_data.csv',
            if it does not already exists, and writing all of the logged data in there. The dashboard will periodically
            read the same csv to display the information.


"""