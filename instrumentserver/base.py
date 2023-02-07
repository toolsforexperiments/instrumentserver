import zmq
import json

from .blueprints import to_dict, deserialize_obj


def encode(data):
    return json.dumps(to_dict(data))


def decode(data):
    return deserialize_obj(json.loads(data))


def send(socket, data):
    return socket.send_string(encode(data))


def recv(socket):
    return decode(socket.recv_string())


def sendBroadcast(socket, name, message):
    """
    broadcasts the message. It will send 2 messages: First the name with the send more flag,
        followed by the message.

    :param socket: The socket sending it.
    :param name: The name of the object, it will be the first part.
    :param messages: The data to send.
    """
    socket.send_string(name, flags=zmq.SNDMORE)
    socket.send_string(encode(message))


def recvMultipart(socket):
    """
    Recieves the broadcast from a broadcast message. It should consist of 2 parts:
     The first item is the name of the object sending it. Second part the message
    """
    messages = socket.recv_multipart()
    return messages[0].decode("utf-8"), decode(messages[1])
