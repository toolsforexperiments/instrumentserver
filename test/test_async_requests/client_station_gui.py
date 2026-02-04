import sys
from pathlib import Path
from instrumentserver.client import ClientStation
from instrumentserver.client.application import ClientStationGui

from instrumentserver import  QtWidgets
if __name__ == "__main__":
    # gather some test config files

    config_path = Path("./serverConfig.yml")

    # create client station
    app = QtWidgets.QApplication(sys.argv)
    cli_station = ClientStation(host="localhost", config_path=config_path)#, param_path=param_path, port=5555)
    
    # test client station functions
    print(cli_station.get_parameters()["test1"]["param1"])
    test1 = cli_station["test1"]
    print(test1.get_random())
    
    # make and display gui window
    win = ClientStationGui(cli_station)
    win.show()
    sys.exit(app.exec_())
    
    
