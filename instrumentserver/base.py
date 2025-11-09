import zmq
import json
import logging

from .blueprints import to_dict, deserialize_obj

logger = logging.getLogger(__name__)

def encode(data):
    return json.dumps(to_dict(data))


def decode(data):
    return deserialize_obj(json.loads(data))


def send(socket, data, use_string=True):
    payload = encode(data)
    if use_string:
        return socket.send_string(payload)
    else:
        return socket.send(payload.encode('utf-8'))


def recv(socket):
    # Try multipart receive first (ROUTER replies)
    parts = socket.recv_multipart()
    while socket.getsockopt(zmq.RCVMORE):
        leftover = socket.recv()
        logger.warning(f"Additional part found in recv: {leftover}")
    if len(parts) == 1:
        data = parts[0]
    elif len(parts) == 2 and parts[0] == b'':  # optional empty delimiter
        data = parts[1]
    else:
        data = parts[-1]  # assume last part is the actual message
    return decode(data)


def send_router(socket, identity, message):
    socket.setsockopt(zmq.SNDTIMEO, 5000)
    socket.setsockopt(zmq.LINGER, 0)
    payload = encode(message).encode('utf-8')
    socket.send_multipart([identity, b'', payload])


def recv_router(socket):
    parts = socket.recv_multipart()
    if len(parts) == 2:
        identity, payload = parts
    elif len(parts) == 3 and parts[1] == b'':
        identity, payload = parts[0], parts[2]
    else:
        raise ValueError(f"Malformed ROUTER message: {parts}")
    return identity, decode(payload)


def sendBroadcast(socket, name, message):
    """
    broadcasts the message. It will send 2 messages: First the name with the send more flag,
        followed by the message.

    :param socket: The socket sending it.
    :param name: The name of the object, it will be the first part.
    :param messages: The data to send.
    """
    socket.send_string(name, flags=zmq.SNDMORE)
    socket.send(encode(message).encode('utf-8'))


def recvMultipart(socket):
    """
    Recieves the broadcast from a broadcast message. It should consist of 2 parts:
     The first item is the name of the object sending it. Second part the message
    """
    messages = socket.recv_multipart()
    return messages[0].decode("utf-8"), decode(messages[1])
