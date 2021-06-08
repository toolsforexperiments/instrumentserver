config = {
    'Fridge temps 1': {
        'PT2 Head': {
            'source_type': 'parameter',
            'parameter_path': 'triton.T1',
            'server': 'localhost',
            'port': 5555,
            'options': {
                'interval': 10000
            },
        },

        'PT2 Plate': {
            'source_type': 'parameter',
            'parameter_path': 'triton.T2',
            'server': 'localhost',
            'port': 5555,
            'options': {
                'interval': 10000
            },
        },

        'Still PLate': {
            'source_type': 'parameter',
            'parameter_path': 'triton.T3',
            'server': 'localhost',
            'port': 5555,
            'options': {
                'interval': 10000
            },
        },

        'Cold Plate': {
            'source_type': 'parameter',
            'parameter_path': 'triton.T4',
            'server': 'localhost',
            'port': 5555,
            'options': {
                'interval': 10000
            },
        },
    },

    'Fridge temps 2': {
        'MC Plate Cernox': {
            'source_type': 'parameter',
            'parameter_path': 'triton.T5',
            'server': 'localhost',
            'port': 5555,
            'options': {
                'interval': 10000
            },
        },

        'PT1 Head': {
            'source_type': 'parameter',
            'parameter_path': 'triton.T6',
            'server': 'localhost',
            'port': 5555,
            'options': {
                'interval': 10000
            },
        },

        'PT1 Plate': {
            'source_type': 'parameter',
            'parameter_path': 'triton.T7',
            'server': 'localhost',
            'port': 5555,
            'options': {
                'interval': 10000
            },
        },

        'MC Plate RuO2': {
            'source_type': 'parameter',
            'parameter_path': 'triton.T8',
            'server': 'localhost',
            'port': 5555,
            'options': {
                'interval': 10000
            },
        },
    },

    'options': {
        'refresh_rate': 30000,
        'allowed_ip': ['*']
        }
    }






config_original_draft = {
    'fridge temps': {  # this is the name of the plot
        'KK MC RuOx [K]': {
            'source_type': 'parameter',
            'parameter_path': 'triton.temperature_channel_10',
            'server': 'localhost',
            'port': 5555,
            'options': {
                'interval': 10,
            },
        },

        'Qubit Pi Pulse length [ns]': {
            'source_type': 'broadcast',
            'parameter_path': 'parameters.qubit.pipulse.len',
            'server': 'localhost',
            'port': 5556,
            'options': {
                'actions': ['parameter-set',],
            },
        }
    },
}