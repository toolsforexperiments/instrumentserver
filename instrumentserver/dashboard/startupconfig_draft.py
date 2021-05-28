config = {
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