# About InstrumentServer

InstrumentServer is part of the [Tools For Experiments](https://github.com/toolsforexperiments) initiative—a collection of software tools developed by the [Pfaff-lab at the University of Illinois at Urbana-Champaign](https://pfaff.physics.illinois.edu/).

## Purpose

InstrumentServer solves the problem of remote instrument access in modern laboratories. Whether you need to control laboratory equipment from a different machine, enable multiple researchers to access the same instruments simultaneously, or build distributed measurement systems, InstrumentServer provides a robust, scalable solution.

## Design Philosophy

InstrumentServer is built on practical experience with real laboratory needs:

- **Simplicity**: Uses well-established ZMQ messaging patterns and QCoDeS integration
- **Reliability**: Per-instrument locking ensures thread-safe concurrent access
- **Performance**: Asynchronous request handling with concurrent instrument control
- **Transparency**: Proxy objects provide native Python interfaces to remote instruments

## Contributing

InstrumentServer is open source and welcomes contributions. Visit the [GitHub repository](https://github.com/toolsforexperiments/instrumentserver) to report issues, submit pull requests, or participate in development.

## Citation

If you use InstrumentServer in your research, please cite the project:

```
@software{instrumentserver,
  title={InstrumentServer: Distributed QCoDeS Instrument Control},
  author={Pfaff, Wolfgang},
  url={https://github.com/toolsforexperiments/instrumentserver},
  year={2020}
}
```