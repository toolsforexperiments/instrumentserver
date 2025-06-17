# -*- coding: utf-8 -*-

import os
import json
import argparse
from typing import Dict, Any, Optional

from qcodes import Instrument
from instrumentserver.client import Client
from instrumentserver.client import ProxyInstrument


class DeviceInitializer:
    def __init__(self, config_file: Optional[str] = None):
        """Initialize the device manager with optional config file."""
        self.client = Client()
        self.config_file = config_file
        self.devices = {}
        
        if config_file and os.path.exists(config_file):
            self.load_config(config_file)

    def load_config(self, config_file: str) -> None:
        """Load device configuration from a JSON file."""
        with open(config_file, 'r') as f:
            config = json.load(f)
            for device_name, device_config in config.items():
                self.add_device(device_name, device_config)

    def add_device(self, name: str, config: Dict[str, Any]) -> ProxyInstrument:
        """Add a single device with the given configuration."""
        if name in self.devices:
            return self.devices[name]

        instrument_class = config.get('instrument_class')
        if not instrument_class:
            raise ValueError(f"instrument_class not specified for device {name}")

        # Remove instrument_class from config as it's not a device parameter
        device_params = config.copy()
        device_params.pop('instrument_class', None)

        device = self.client.find_or_create_instrument(
            name=name,
            instrument_class=instrument_class,
            **device_params
        )
        
        self.devices[name] = device
        return device

    def get_device(self, name: str) -> Optional[ProxyInstrument]:
        """Get a device by name."""
        return self.devices.get(name)

    def list_devices(self) -> Dict[str, ProxyInstrument]:
        """List all initialized devices."""
        return self.devices.copy()

    def close_all(self) -> None:
        """Close all initialized devices."""
        Instrument.close_all()
        self.devices.clear()


def main(config_file: Optional[str] = None, **kwargs):
    """Main function to initialize devices."""
    Instrument.close_all()
    return DeviceInitializer(config_file)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Device initialization tool")
    parser.add_argument("--config", type=str, help="Path to device configuration file")
    parser.add_argument("--p", type=str, help="Port (deprecated, use config file instead)")
    args = parser.parse_args()
    
    main(config_file=args.config, **vars(args))
