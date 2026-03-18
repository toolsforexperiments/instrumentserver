"""
If any instrument in the config does not have values for SERVERFIELDS or GUIFIELD, the values inside of it are added
to the config as defaults. If you are adding any extra fields to the config make sure to add the default values on those
variables since we parse the config using those.
"""
import io
import tempfile
from typing import IO, Any

import ruamel.yaml  # type: ignore[import-untyped] # Known bugfix under no-fix status: https://sourceforge.net/p/ruamel-yaml/tickets/328/
from pathlib import Path

# Centralised point of extra fields for the server with its default as value
SERVERFIELDS = {'initialize': True}

# Extra fields for the GUI.
GUIFIELD = {'type': 'instrumentserver.gui.instruments.GenericInstrument', 'kwargs': {}}


def loadConfig(configPath: str | Path) -> tuple[str, dict, dict, IO[bytes], dict, dict]:
    """
    Loads the config for the instrumentserver. From 1 config file it splits the respective fields into 3 different
    objects: a serverConfig (the configurations for the server), a stationConfig(the qcodes station config file clean
    of any extra config fields), and a GUI config file (any config that the GUI of the server needs).

    The qcodes station only accepts the path of an actual file for its config. So after loading the YAML file,
    the added fields are removed from the loaded dictionary. After that it is converted to a byte stream and written
    into a temporary file. what is returned here is the path to that temporary file, after the station loads the
    file, it gets deleted automatically

    The config also supports a 'gui_defaults' section for class-based GUI configuration that applies to all
    instances of a given instrument class. These defaults are merged with instance-specific configs.
    """
    configPath = Path(configPath)
    serverConfig: dict = {}  # Config for the server
    guiConfig = {}  # Individual gui config of each instrument
    fullConfig = {}  # serverConfig + guiConfig + any unfilled fields. Used for creating instruments from the gui
    pollingRates = {}  # Polling rates for each parameter
    ipAddresses = {} # Dictionary of IP Addresses to send broadcasts to:
    # externalBroadcast: where to externally send parameter change broadcasts to, formatted like "tcp://address:port"
    # listeningAddress: additional address to listen to messages received by the server, formatted like "address"

    yaml = ruamel.yaml.YAML()
    rawConfig = yaml.load(configPath)

    if "instruments" not in rawConfig:
        raise AttributeError("All configurations must be inside the 'instruments' field. "
                             "Try adding 'instruments:' at the top of the config file and "
                             "indenting everything underneath.")

    # Parse gui_defaults section (class-based GUI configuration)
    gui_defaults = {}
    if 'gui_defaults' in rawConfig:
        gui_defaults = rawConfig.pop('gui_defaults')

    # Removing any extra fields
    for instrumentName, configDict in rawConfig['instruments'].items():
        serverConfig[instrumentName] = {}
        for field, default in SERVERFIELDS.items():
            if field in configDict:
                fieldSetting = configDict.pop(field)
                if fieldSetting is None:
                    raise AttributeError(f'"{field}" field cannot be None')
                serverConfig[instrumentName][field] = fieldSetting
            else:
                serverConfig[instrumentName][field] = default

        # we don't go through the entire gui because generic is a special setting
        # and we only have 2 different options for now
        if 'gui' in configDict:
            guiDict = configDict.pop('gui')
            if guiDict is None:
                raise AttributeError(f'"gui" field cannot be None')
            if 'type' in guiDict:
                if guiDict['type'] == 'generic' or guiDict['type'] == 'Generic':
                    guiDict['type'] = GUIFIELD['type']
            # If the user does not specify a gui, the default one will be used
            else:
                guiDict['type'] = GUIFIELD['type']

            guiConfig[instrumentName] = guiDict
        else:
            guiConfig[instrumentName] = GUIFIELD

        if 'pollingRate' in configDict:
            ratesDict = configDict.pop('pollingRate')
            # This catches the case when the pollingRate is in the config but it is empty.
            if isinstance(ratesDict, dict):
                pollingRates.update({instrumentName + "." + param: rate for param, rate in ratesDict.items()})

        fullConfig[instrumentName] = {'gui': guiConfig[instrumentName], **configDict, **serverConfig[instrumentName]}

    # Merge gui_defaults into guiConfig for each instrument
    if gui_defaults:
        for instrumentName in guiConfig.keys():
            # Get instrument class name from the type field
            instrument_type = fullConfig[instrumentName].get('type', '')
            class_name = instrument_type.split('.')[-1] if instrument_type else ''

            # Initialize kwargs if not present
            if 'kwargs' not in guiConfig[instrumentName]:
                guiConfig[instrumentName]['kwargs'] = {}

            # Merge patterns in order: __default__ → class → instance
            # For each GUI config key (parameters-hide, methods-hide, etc.)
            for config_key in ['parameters-hide', 'methods-hide', 'parameters-star', 'parameters-trash',
                               'methods-star', 'methods-trash']:
                merged_patterns = []

                # 1. Add patterns from __default__
                if '__default__' in gui_defaults:
                    default_config = gui_defaults['__default__']
                    if config_key in default_config:
                        merged_patterns.extend(default_config[config_key])

                # 2. Add patterns from class-specific defaults
                if class_name and class_name in gui_defaults:
                    class_config = gui_defaults[class_name]
                    if config_key in class_config:
                        merged_patterns.extend(class_config[config_key])

                # 3. Add patterns from instance-specific config
                if config_key in guiConfig[instrumentName]['kwargs']:
                    merged_patterns.extend(guiConfig[instrumentName]['kwargs'][config_key])

                # Store merged patterns if any exist
                if merged_patterns:
                    guiConfig[instrumentName]['kwargs'][config_key] = merged_patterns

            # Update fullConfig with merged GUI config
            fullConfig[instrumentName]['gui'] = guiConfig[instrumentName]

    # Gets all of the broadcasting and listening addresses from the config file
    if 'networking' in rawConfig:
        addressDict = rawConfig['networking']
        if addressDict is not None:
            for address in addressDict.items():
                ipAddresses.update({address[0]: address[1]})
        rawConfig.pop('networking')

    # Creating the file like object
    with io.BytesIO() as ioBytesFile:
        yaml.dump(rawConfig, ioBytesFile)
        stationConfig = ioBytesFile.getvalue()

    # Storing the file like object in a temporary file to pass to the station config
    tempFile = tempfile.NamedTemporaryFile(delete=False)
    tempFile.write(stationConfig)
    tempFile.seek(0)
    tempFilePath = tempFile.name

    # You need to return the tempFile itself so that the garbage collector doesn't touch it
    return tempFilePath, serverConfig, fullConfig, tempFile, pollingRates, ipAddresses
