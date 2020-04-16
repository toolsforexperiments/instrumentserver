import pickle

def encode(data):
    return pickle.dumps(data)


def decode(data):
    return pickle.loads(data)


def send(socket, data):
    return socket.send_pyobj(encode(data))


def recv(socket):
    return decode(socket.recv_pyobj())