"""Unit tests for instrumentserver.base encode/decode and send/recv.

Note: encode/decode in this module is designed to work with blueprint objects
that implement .toJson() — it is not a general-purpose JSON encoder.
"""

import time

import pytest
import zmq

from instrumentserver.base import (
    decode,
    encode,
    recv,
    recvMultipart,
    send,
    sendBroadcast,
)
from instrumentserver.blueprints import (
    Operation,
    ParameterBroadcastBluePrint,
    ServerInstruction,
)

# ---------------------------------------------------------------------------
# encode / decode (blueprint objects only)
# ---------------------------------------------------------------------------


def test_encode_broadcast_blueprint_returns_string():
    bp = ParameterBroadcastBluePrint(
        name="p", action="parameter-update", value=42, unit="V"
    )
    result = encode(bp)
    assert isinstance(result, str)


def test_encode_decode_broadcast_blueprint_round_trip():
    bp = ParameterBroadcastBluePrint(
        name="p", action="parameter-update", value=42, unit="V"
    )
    encoded = encode(bp)
    decoded = decode(encoded)
    assert isinstance(decoded, ParameterBroadcastBluePrint)
    assert decoded.name == "p"
    assert decoded.value == 42
    assert decoded.unit == "V"
    assert decoded.action == "parameter-update"


def test_encode_decode_server_instruction_round_trip():
    instr = ServerInstruction(operation=Operation.get_existing_instruments)
    encoded = encode(instr)
    decoded = decode(encoded)
    assert isinstance(decoded, ServerInstruction)
    # operation is stored/restored as its string name
    assert decoded.operation in (
        Operation.get_existing_instruments,
        Operation.get_existing_instruments.name,
        Operation.get_existing_instruments.value,
    )


def test_decode_string_is_returned_as_is():
    """encode wraps the string; decode should round-trip it."""
    s = '{"key": "value"}'
    # encode on a plain string calls to_dict which returns it unchanged,
    # then json.dumps wraps it as a JSON string
    encoded = encode(s)
    decoded = decode(encoded)
    # decoded is the original string (json.loads unwraps, deserialize_obj tries
    # to parse it as JSON again and returns the inner dict)
    assert decoded == {"key": "value"}


# ---------------------------------------------------------------------------
# send / recv  (using zmq PAIR sockets with blueprint objects)
# ---------------------------------------------------------------------------


@pytest.fixture
def zmq_pair():
    ctx = zmq.Context()
    s1 = ctx.socket(zmq.PAIR)
    s2 = ctx.socket(zmq.PAIR)
    port = s1.bind_to_random_port("tcp://127.0.0.1")
    s2.connect(f"tcp://127.0.0.1:{port}")
    for s in (s1, s2):
        s.setsockopt(zmq.RCVTIMEO, 2000)
        s.setsockopt(zmq.LINGER, 0)
    yield s1, s2
    s1.close()
    s2.close()
    ctx.term()


def test_send_recv_broadcast_blueprint(zmq_pair):
    s1, s2 = zmq_pair
    bp = ParameterBroadcastBluePrint(
        name="my_p", action="parameter-update", value=7, unit="Hz"
    )
    send(s1, bp)
    result = recv(s2)
    assert isinstance(result, ParameterBroadcastBluePrint)
    assert result.name == "my_p"
    assert result.value == 7


def test_send_recv_server_instruction(zmq_pair):
    s1, s2 = zmq_pair
    instr = ServerInstruction(operation=Operation.get_existing_instruments)
    send(s1, instr)
    result = recv(s2)
    assert isinstance(result, ServerInstruction)
    assert result.operation in (
        Operation.get_existing_instruments,
        Operation.get_existing_instruments.name,
        Operation.get_existing_instruments.value,
    )


# ---------------------------------------------------------------------------
# sendBroadcast / recvMultipart  (PUB/SUB)
# ---------------------------------------------------------------------------


@pytest.fixture
def zmq_pub_sub():
    ctx = zmq.Context()
    pub = ctx.socket(zmq.PUB)
    sub = ctx.socket(zmq.SUB)
    port = pub.bind_to_random_port("tcp://127.0.0.1")
    sub.connect(f"tcp://127.0.0.1:{port}")
    sub.setsockopt_string(zmq.SUBSCRIBE, "")
    sub.setsockopt(zmq.RCVTIMEO, 2000)
    pub.setsockopt(zmq.LINGER, 0)
    sub.setsockopt(zmq.LINGER, 0)
    time.sleep(0.05)
    yield pub, sub
    pub.close()
    sub.close()
    ctx.term()


def test_sendBroadcast_recvMultipart(zmq_pub_sub):
    pub, sub = zmq_pub_sub
    bp = ParameterBroadcastBluePrint(
        name="my_param", action="parameter-update", value=7, unit="V"
    )
    sendBroadcast(pub, "my_param", bp)
    name, result = recvMultipart(sub)
    assert name == "my_param"
    assert isinstance(result, ParameterBroadcastBluePrint)
    assert result.value == 7


def test_sendBroadcast_name_prefix_matches(zmq_pub_sub):
    pub, sub = zmq_pub_sub
    bp = ParameterBroadcastBluePrint(name="ins.param", action="parameter-set", value=42)
    sendBroadcast(pub, "ins.param", bp)
    name, result = recvMultipart(sub)
    assert name == "ins.param"
