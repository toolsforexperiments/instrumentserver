import argparse
import logging

from instrumentserver import setupLogging, logger
from instrumentserver.client import StationClient


setupLogging()
log = logger()
log.setLevel(logging.DEBUG)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Testing the client')
    parser.add_argument("--message", help="message to send")
    args = parser.parse_args()

    print('message:', args.message)
    # print(args.message)
    # cli = StationClient()
    # cli.connect()
    # cli.ask(args.message)
