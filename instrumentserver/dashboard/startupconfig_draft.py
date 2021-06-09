config = {
    'Random Numbers 1': {
        'Param 0': {
            'source_type': 'parameter',
            'parameter_path': 'test.param0',
            'server': 'localhost',
            'port': 5555,
            'options': {
                'interval': 5000
            }
        },
        'Param 1': {
            'source_type': 'parameter',
            'parameter_path': 'test.param1',
            'server': 'localhost',
            'port': 5555,
            'options': {
                'interval': 5000
            }
        },
        'Param 4': {
            'source_type': 'parameter',
            'parameter_path': 'test.param4',
            'server': 'localhost',
            'port': 5555,
            'options': {
                'interval': 5000
            }
        }

    },
    'Random Numbers 2': {
        'Param 2': {
            'source_type': 'parameter',
            'parameter_path': 'test.param2',
            'server': 'localhost',
            'port': 5555,
            'options': {
                'interval': 5000
            }
        },
        'Param 3': {
            'source_type': 'parameter',
            'parameter_path': 'test.param3',
            'server': 'localhost',
            'port': 5555,
            'options': {
                'interval': 5000
            }
        }
    }
}












config_fridge_example = {
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