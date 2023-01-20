import io
import tempfile

import ruamel.yaml
from pathlib import Path

# Centralised point of extra fields for the server with its default as value
SERVERFIELDS = {'initialize': True}

# Extra fields for the GUI.
GUIFIELD = {'gui': 'generic'}

def loadConfig(configPath: str):
    """
    Loads the config for the instrumentserver. From 1 config file it splits the respective fields into 3 different
    objects: a serverConfig (the configurations for the server), a stationConfig(the qcodes station config file clean
    of any extra config fields), and a GUI config file (any config that the GUI of the server needs.

    The qcodes station only accepts the path of an actual file for its config. So after loading the YAML file, the added
    fields are removed from the loaded dictionary. After that it is converted to a byte stream and written into a temporary file.
    what is returned here is the path to that temporary file, after the station loads the file, it gets deleted automatically
    """
    configPath = Path(configPath)
    serverConfig = {}
    guiConfig = {}
    stationConfig = None

    yaml = ruamel.yaml.YAML()
    rawConfig = yaml.load(configPath)

    # Removing any extra fields
    for instrumentName, configDict in rawConfig['instruments'].items():
        serverConfig[instrumentName] = {}
        for field, default in SERVERFIELDS.items():
            if field in configDict:
                serverConfig[instrumentName][field] = configDict.pop(field)
            else:
                serverConfig[instrumentName][field] = default
        guiConfig[instrumentName] = {}
        for field, default in GUIFIELD.items():
            if field in configDict:
                guiConfig[instrumentName][field] = configDict.pop(field)
            else:
                guiConfig[instrumentName][field] = default

    # Creating the file like object
    with io.BytesIO() as ioBytesFile:
        yaml.dump(rawConfig, ioBytesFile)
        stationConfig = ioBytesFile.getvalue()

    # Storing the file like object in a temporary file to pass to the station config
    tempFile = tempfile.NamedTemporaryFile()
    tempFile.write(stationConfig)
    tempFile.seek(0)
    tempFilePath = tempFile.name

    # You need to return the tempFile itself so that the garbage collector doesn't touch it
    return tempFilePath, serverConfig, guiConfig, tempFile
















