# Measurement Protocol

When start doing experiment, the following protocol should start by steps

## Initialization of instrument server (kernel 1)

run xxx.py to initialize the main kernel.

## Initialization of measurement client (kernel 2)

1. Start a new kernel;
2. Run main.py to start the measurement initialization.

## Monitor and configure the current instruments
	
Using the generated window to monitor all parameters changed and also make the needed change for the later measurement. 
	
## Write and run the measurement script

To run the real measurement, the following you can do:
- write your own measurement script;
- load the old script;
- load the integrated measurement window.

Running the command in kernel 2.

## Save and plot the data

Configure the saving and plotting class to have live functionality.
