import sys
from instrumentserver.client import ClientStation
from instrumentserver.client.application import ClientStationGui

from instrumentserver import  QtWidgets
if __name__ == "__main__":
    # gather some test config files
    import os
    current = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(current, "./client_instruments.yaml")
    param_path = os.path.join(current, "./client_params.json")
    hide_config = os.path.join(current, "./hide_attributes.yaml")

    # create client station
    app = QtWidgets.QApplication(sys.argv)
    cli_station = ClientStation(host="localhost", init_instruments=config_path, param_path=param_path, port=5555)
    
    # test client station functions
    print(cli_station.get_parameters()["test1"]["param1"])
    test1 = cli_station["test1"]
    print(test1.get_random())
    
    # make and display gui window
    win = ClientStationGui(cli_station, hide_config)
    win.show()
    sys.exit(app.exec_())
    
    
