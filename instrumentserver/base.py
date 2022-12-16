import json

from .blueprints import to_dict, from_dict


def encode(data):
    return json.dumps(to_dict(data))


def decode(data):
    return from_dict(json.loads(data))


def send(socket, data):
    return socket.send_string(encode(data))


def recv(socket):
    return decode(socket.recv_string())
