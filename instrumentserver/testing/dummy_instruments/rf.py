from typing import Any, Dict, Union, Tuple
import numpy as np
from scipy import constants

from qcodes import Instrument, ParameterWithSetpoints
from qcodes.utils import validators


class ResonatorResponse(Instrument):
    """A dummy instrument that generates the response of a resonator measured in
    reflection.

    Behavior is essentially that of a VNA, with the resonator and system
    properties added as parameters.
    """

    def __init__(self, name, f0=5e9, df=1e6, **kw):
        super().__init__(name, **kw)

        # add params of the resonator and the virtual detection chain
        self.add_parameter('resonator_frequency', set_cmd=None, unit='Hz',
                           vals=validators.Numbers(1, 50e9),
                           initial_value=f0)
        self.add_parameter('resonator_linewidth', set_cmd=None, unit='Hz',
                           vals=validators.Numbers(1, 1e9),
                           initial_value=df)
        self.add_parameter('noise_temperature', set_cmd=None, unit='K',
                           vals=validators.Numbers(0.05, 3000),
                           initial_value=4.0)
        self.add_parameter('input_attenuation', set_cmd=None, unit='dB',
                           vals=validators.Numbers(0, 200),
                           initial_value=70)

        # actual instrument parameters
        self.add_parameter('start_frequency', set_cmd=None, unit='Hz',
                           vals=validators.Numbers(20e3, 19.999e9),
                           initial_value=20e3)
        self.add_parameter('stop_frequency', set_cmd=None, unit='Hz',
                           vals=validators.Numbers(20.1e3, 20e9),
                           initial_value=20e9)
        self.add_parameter('npoints', set_cmd=None, vals=validators.Ints(2, 40001),
                           initial_value=1601)
        self.add_parameter('bandwidth', set_cmd=None, unit='Hz',
                           vals=validators.Numbers(1, 1e6), initial_value=10e3)
        self.add_parameter('power', set_cmd=None, unit='dBm',
                           vals=validators.Numbers(-100, 0), initial_value=-100)

        # data parameters
        self.add_parameter('frequency', unit='Hz',
                           vals=validators.Arrays(shape=(self.npoints.get_latest,)),
                           get_cmd=self._frequency_vals,
                           snapshot_value=False, )
        self.add_parameter('data',
                           parameter_class=ParameterWithSetpoints,
                           setpoints=[self.frequency, ],
                           vals=validators.Arrays(
                               shape=(self.npoints.get_latest,),
                               valid_types=[np.complexfloating],
                           ),
                           get_cmd=self._get_data, )

    def calibrate(self) -> Dict[str, Union[tuple, Any]]:
        """perform a calibration of some sort."""
        return True

    def setup_stuff(self, a_parameter: int, another_parameter: float = 5.0,
                    *arg, **kw: Any) -> bool:
        """setting up."""
        return True

    def poorly_annotated_function(self, x, y, *, z=5, **kwargs):
        return 10

    # private utility methods
    def _frequency_vals(self):
        return np.linspace(self.start_frequency(), self.stop_frequency(), self.npoints())

    def _get_data(self):
        fvals = self._frequency_vals()
        data = self._resonator_reflection_signal(
            fvals,
            self.resonator_frequency(),
            self.resonator_linewidth(),
            self.power() - self.input_attenuation(),
            self.bandwidth(),
            self.noise_temperature())

        return data

    def _resonator_reflection_signal(self, fvals, f0, df, P_in, BW, T_N):
        """Compute a realistic resonator reflection signal of a one-port
        resonator, including random noise.

        :param fvals: probe frequencies [Hz]
        :param f0: resonance frequency [Hz]
        :param df: line width [Hz]
        :param P_in: incident power [dBm]
        :param BW: detection bandwidth [Hz]
        :param T_N: noise temperature [K]

        :returns: dummy data, same shape as `fvals`.
        """
        det = fvals - f0
        pwr = 1e-3 * 10 ** (P_in / 10)  # convert dBm to Watt
        ideal_signal = (2j * det - df) / (2j * det + df)
        noise = (constants.k * T_N * BW / pwr) ** .5
        noise_real = np.random.normal(size=ideal_signal.size, loc=0, scale=noise)
        noise_imag = np.random.normal(size=ideal_signal.size, loc=0, scale=noise)
        return ideal_signal + noise_real + 1j * noise_imag


class Generator(Instrument):

    def __init__(self, name, *arg, **kw):
        super().__init__(name, *arg, **kw)

        self.add_parameter('frequency', unit='Hz',
                           set_cmd=None,
                           vals=validators.Numbers(1e3, 20e9),
                           initial_value=10e9)

        self.add_parameter('power', unit='dBm',
                           set_cmd=None,
                           vals=validators.Numbers(-100, 25),
                           initial_value=-100)

        self.add_parameter('rf_on', set_cmd=None,
                           vals=validators.Bool(),
                           initial_value=False)
