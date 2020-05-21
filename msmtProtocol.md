# Measurement Protocol

When start doing experiment, the following protocol should start by steps

## Initialization of instrument server (kernel 1)
### User need to:
1. (Optional) Create/edit the [YAML configuration file](http://qcodes.github.io/Qcodes/examples/Station.html?highlight=configuration#Configuring-the-Station-by-using-a-YAML-configuration-file) to define what
 instruments will be created in the server and their initial conditions.
2. Run "start_server.py" to initialize the main kernel. 

### The program will:
* Load the YAML file and initialize the instruments.
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
### User needs to:
1. Start a new kernel;
2. Instantiate proxy instruments that are needed for the experiment, which can
 be done by (either or both):
    1. write `my_instruemnt = InstrumentProxy('target_instruemnt_name')` manually 
    2. load from JSON (/YAML?) file.
    
### The program will:   
* Look for instrument with name 'target_instruemnt_name' on the server and
 build a proxy for it. Later user can use these proxy instrument to write
  measurement codes.
* An instrument GUI will popup, which will show instrument parameters, and
 give access to change parameters and call functions.   
 
### Notice and suggestions:
* For any given measurement, 

### _TODO:_
* we need to define a format for saving instrument configuration at this stage
, should we use the same format as the qcodes one? Also a helper function need
 to be written for loading and saving the configuration file.
* RK: I think that the instrumentserver.serialize() function is pretty easy to use. 
It just saves to a JSON format 

### _Question and discussion:_
* should we run this code at this step and later run the measurement code in
 the same kernel, or write this part and the measurement part in one file and
  run them together?
    * RK: If we wrote a seperate module that had a function like "initialize" that took in the instruments, filename, and cwd 
    (with the default being the console cwd that the script was created in) then it could handle this in a standard way by 
    creating the right folder structure. The benefit of doing it this way is that it would be a standard import, but still explicitly 
    have the line in the measurement code that would tell you exactly where and when everything was saved
  
  
## Monitor and configure the current instruments
### User need to:
Using the generated window to monitor all parameters changed and also make the needed change for the later measurement. 

### Notice and suggestions:
* Always remember to refresh the current instrument status after control
 instrument by touching the physical device.
    * RK: This is tricky with USB instruments, especially. Will we have to do periodic parameter.get() calls to make sure everything is in synch? 
    For all of the parameters in an instrument, that is a lot of commands if you want it up to date within 100ms

 
 

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
   * RK: I agree with this, the measurement function should just need a function with a cwd and the instruments you choose. 
   * RK: If the measurement will essentially be its own class, should we make it a station? 
   That way the sweep variables could be held as parameters in the station and we can use the validators etc.
 
 
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
   * I think this depends on Wolfgang's file format. If it can support this, I would say we should use it. 

## Possible File Structures
Data:
- date
  - Project_name
    - Run_name_person (incrementNumber_string_string)
      - Instrument_settings.JSON
      - Data.hdf5
    