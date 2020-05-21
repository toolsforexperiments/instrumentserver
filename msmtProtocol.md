# Measurement Protocol

When start doing experiment, the following protocol should start by steps

## Initialization of instrument server (kernel 1)
### User need to:
1. (Optional) Create/edit the [YAML configuration file](http://qcodes.github.io/Qcodes/examples/Station.html?highlight=configuration#Configuring-the-Station-by-using-a-YAML-configuration-file) to define what
 instruments will be created in the server and their initial conditions.
2. Run "start_server.py" to initialize the main kernel. 

### What will happen after user have done that:
* The start_server program will load the YAML file and initialize the
 instruments.
* A `zmq.REP` server socket will be created and wait for commands from clients.
* A server GUI will popup, which will list the instruments on the server
, show logging information and give access to some basic operation of the
 server (e.g. change server address)

### Notice and suggestions:
* The "start_server.py" should be really robust and shouldn't be
 changed by anyone except when we want to do structural upgrade to our code.
* The YAML file should contain the instruments that are connected to the
 computer for relatively long time. (One YAML for each computer or project? ) For
  instruments that we often move around between computers, we can always add
   them later from the client side.


## Initialization of measurement client (kernel 2)
### User need to:
1. Start a new kernel;
2. Instantiate proxy instruments that are needed for the experiment, which can
 be done by (either or both):
    1. write `my_instruemnt = InstrumentProxy('target_instruemnt_name')` manually
    2. load from JSON (/YAML?) file.
    
### What will happen after user have done that:   
* The program will look for instrument with name 'target_instruemnt_name' on
 the server and build a proxy for it. Later user can use these proxy
  instrument to write measurement codes.
* An instrument GUI will popup, which will show instrument parameters, and
 give access to change parameters and call functions.   
 
### Notice and suggestions:
*

### _Question and discussion:_
* should we run this code at this step and later run the measurement code in
 the same kernel, or write this part and the measurement part in one file and
  run them together?
  
  
## Monitor and configure the current instruments
### User need to:
Using the generated window to monitor all parameters changed and also make the needed change for the later measurement. 

### Notice and suggestions:
* Always remember to refresh the current instrument status after control
 instrument by touching the physical device.
 
 

## Write and run the measurement script
### User need to:
1. prepare measurement script by (one or combination of following):
    1. write your own measurement script;
    2. load the old script;
    3. load the integrated measurement window.
    4. load a standardized measurement function (e.g. flux weep), and feed in
     setup parameters. 
2. Run the command in kernel 2.
3. Save measurement parameter.

### Notice and suggestions:
* For the measurements that we do very frequently in a project, it will be
 good to wire the measurement as a standard function, and also save setup
  parameters to a standard format. So that it will be easy to repeat the
   experiment and trace back what we did.  
 
 
## Save and plot the data
### User need to:
1. (Optional) Save the whole measurement script.
2. Configure the saving and plotting class to have live functionality.

### _TODO:_
* We need to have a standardized format for data saving.

### _Question and discussion:_
 * Should we save the data and setup parameters in the same file? I'm concerning
  that sometimes the data can be huge and takes long time to load, but we only
   want to see the setup parameter. 