import argparse
import logging
import json

from instrumentserver import setupLogging, logger
from instrumentserver.client import StationClient


setupLogging()
log = logger()
log.setLevel(logging.DEBUG)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Testing the client')
    parser.add_argument("--message", help="message to send")
    parser.add_argument("--port", default=5555)
    parser.add_argument("--host", default='localhost')
    parser.add_argument("--operation")
    args = parser.parse_args()

    if args.message is not None:
        msg = args.message
    else:
        msg = dict(
            operation=args.operation,
        )

    cli = StationClient()
    cli.connect()
    cli.ask(msg)
