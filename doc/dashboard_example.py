"""
This is an example for a config dictionary for the dashboard/logger. For more information on how to use it check
the documentation on the dashboard.
"""


config = {
    'Random Numbers 1': {
        'Param 0': {
            'source_type': 'parameter',
            'parameter_path': 'test.param0',
            'server': 'localhost',
            'port': 5555,
            'options': {
                'interval': 1
            }
         },
        'Param 1': {
            'source_type': 'parameter',
            'parameter_path': 'test.param1',
            'server': 'localhost',
            'port': 5555,
            'options': {
                'interval': 1
            }
        },
        'Param 4': {
            'source_type': 'parameter',
            'parameter_path': 'test.param4',
            'server': 'localhost',
            'port': 5555,
            'options': {
                'interval': 1
            }
        },

        'Param 2': {
            'source_type': 'parameter',
            'parameter_path': 'test.param2',
            'server': 'localhost',
            'port': 5555,
            'options': {
                'interval': 1
            }
        },
        'Param 3': {
            'source_type': 'parameter',
            'parameter_path': 'test.param3',
            'server': 'localhost',
            'port': 5555,
            'options': {
                'interval': 1
            }
        }
    },

    'options': {
        'refresh_rate': 10,
        'allowed_ip': ['*'],
        'load_and_save': 'C:/Users/Msmt/Documents/dashboard_data.csv'
        }
}