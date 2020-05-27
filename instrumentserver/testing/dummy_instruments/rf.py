from typing import Any, Dict, Union, Tuple
import numpy as np
from scipy import constants

from qcodes import Instrument, ParameterWithSetpoints, InstrumentChannel
from qcodes.utils import validators


class ResonatorResponse(Instrument):
    """A dummy instrument that generates the response of a resonator measured in
    reflection.

    Behavior is essentially that of a VNA, with the resonator and system
    properties added as parameters.
    """

    def __init__(self, name, f0=5e9, df=1e6, **kw):
        super().__init__(name, **kw)

        self._frq_mod = 0.0
        self._frq_mod_multiply = False

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

    def modulate_frequency(self, delta: float = 0, multiply=False) -> None:
        """add an offset to the resonance frequency.

        If `multiply` is ``True``, the change in frequency is the product of `delta`
        and the set frequency. if ``False``, then `delta` is added.
        """
        self._frq_mod = delta
        self._frq_mod_multiply = multiply

    # private utility methods
    def _frequency_vals(self):
        return np.linspace(self.start_frequency(), self.stop_frequency(), self.npoints())

    def _get_data(self):
        f0 = self.resonator_frequency()
        if self._frq_mod_multiply:
            f0 *= self._frq_mod
        else:
            f0 += self._frq_mod

        fvals = self._frequency_vals()
        data = self._resonator_reflection_signal(
            fvals,
            f0,
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
    """A simple dummy that mocks an RF generator."""

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


class FluxControl(Instrument):
    """A dummy that hooks to :class:`.ResonatorResponse` and modifies its
    resonance frequency as if the resonator were a squid."""

    def __init__(self, name: str, resonator_instrument: ResonatorResponse,
                 *args, **kwargs):
        super().__init__(name, *args, **kwargs)

        self._resonator = resonator_instrument

        self.add_parameter('inductive_participation_ratio',
                           set_cmd=None,
                           vals=validators.Numbers(0, 1),
                           initial_value=0.05)

        self.add_parameter('flux', unit='Phi_0',
                           set_cmd=self._set_flux,
                           vals=validators.Numbers(-1, 1),
                           initial_value=0)

    def _set_flux(self, flux):
        mod = 1./(1. + self.inductive_participation_ratio() / np.abs(np.cos(np.pi*flux)))
        self._resonator.modulate_frequency(mod, True)


class DummyChannel(Instrument):
    def __init__(self, name: str, *args, **kwargs):
        super().__init__(name, *args, **kwargs)
        self.add_parameter('ch0',
                           set_cmd=None,
                           vals=validators.Numbers(0, 1),
                           initial_value=0)

        self.add_parameter('ch1', unit='v',
                           set_cmd=None,
                           vals=validators.Numbers(-1, 1),
                           initial_value=1)


class DummyInstrumentWithSubmodule(Instrument):
    """A dummy instrument with submodules"""

    def __init__(self, name: str, *args, **kwargs):
        super().__init__(name, *args, **kwargs)

        self.add_parameter('param0',
                           set_cmd=None,
                           vals=validators.Numbers(0, 1),
                           initial_value=0)

        self.add_parameter('param1', unit='v',
                           set_cmd=None,
                           vals=validators.Numbers(-1, 1),
                           initial_value=1)
        for chan_name in ('A', 'B', 'C'):
            channel = DummyChannel('Chan{}'.format(chan_name))
            self.add_submodule(chan_name, channel)

    def test_func(self, a, b, *args, c=10, **kwargs):
        return a, b, args[0], c, kwargs['d'], self.param0()
