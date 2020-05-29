import argparse
import logging
import json

from instrumentserver import setupLogging, logger
from instrumentserver.client import sendRequest
from instrumentserver.server.core import InstrumentCreationSpec, Operation


setupLogging(addStreamHandler=True, streamHandlerLevel=logging.DEBUG)
log = logger()
log.setLevel(logging.DEBUG)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Testing the client')
    parser.add_argument("--message", help="message to send")
    parser.add_argument("--port", default=5555)
    parser.add_argument("--host", default='localhost')
    parser.add_argument("--operation")
    parser.add_argument("--new_instrument_class")
    parser.add_argument("--new_instrument_args")
    parser.add_argument("--new_instrument_kwargs")
    args = parser.parse_args()

    if args.message is not None:
        msg = args.message
    else:
        msg = dict(
            operation=args.operation,
        )
        if Operation(args.operation) == Operation.create_instrument:
            msg['create_instrument_spec'] = InstrumentCreationSpec(
                instrument_class=args.new_instrument_class,
                args=eval(str(args.new_instrument_args)),
                kwargs=eval(str(args.new_instrument_kwargs))
            )

    sendRequest(msg)
