from qcodes import Parameter, Station
from instrumentserver import startServer, QtWidgets


def make_station():
    from instrumentserver.testing.dummy_instruments.rf import ResonatorResponse
    dummy_vna = ResonatorResponse('dummy_vna')

    from instrumentserver.testing.dummy_instruments.rf import FluxControl
    dummy_flux = FluxControl('dummy_flux', dummy_vna)

    station = Station(dummy_vna, dummy_flux)
    return station


def main():
    station = make_station()
    app = QtWidgets.QApplication([])
    server = startServer(station)

    # add some more stuff through another interface.
    from instrumentserver.testing.dummy_instruments.rf import Generator
    rf_src = Generator('rf_src')
    lo_src = Generator('lo_src')
    qubit_src = Generator('qubit_src')
    for c in rf_src, lo_src, qubit_src:
        server.addStationComponent(c)

    return app.exec_()


if __name__ == '__main__':
    main()
