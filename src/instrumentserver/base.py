import json
import logging
from collections.abc import Callable
from typing import Any, Tuple, Union

import zmq

from .blueprints import ParameterBroadcastBluePrint, deserialize_obj, to_dict

logger = logging.getLogger(__name__)


def encode(data: Any) -> str:
    return json.dumps(to_dict(data))


def decode(data: Union[str, bytes]) -> Any:
    return deserialize_obj(json.loads(data))


def send(socket: "zmq.Socket", data: Any, use_string: bool = True) -> Any:
    payload = encode(data)
    if use_string:
        return socket.send_string(payload)
    else:
        return socket.send(payload.encode("utf-8"))


def recv(socket: "zmq.Socket") -> Any:
    # Try multipart receive first (ROUTER replies)
    parts = socket.recv_multipart()
    while socket.getsockopt(zmq.RCVMORE):
        leftover = socket.recv()
        logger.warning(f"Additional part found in recv: {leftover!r}")
    if len(parts) == 1:
        data = parts[0]
    elif len(parts) == 2 and parts[0] == b"":  # optional empty delimiter
        data = parts[1]
    else:
        data = parts[-1]  # assume last part is the actual message
    return decode(data)


def send_router(socket: "zmq.Socket", identity: bytes, message: Any) -> None:
    socket.setsockopt(zmq.SNDTIMEO, 5000)
    socket.setsockopt(zmq.LINGER, 0)
    payload = encode(message).encode("utf-8")
    socket.send_multipart([identity, b"", payload])


def recv_router(socket: "zmq.Socket") -> Tuple[bytes, Any]:
    parts = socket.recv_multipart()
    if len(parts) == 2:
        identity, payload = parts
    elif len(parts) == 3 and parts[1] == b"":
        identity, payload = parts[0], parts[2]
    else:
        raise ValueError(f"Malformed ROUTER message: {parts}")
    return identity, decode(payload)


def sendBroadcast(socket: "zmq.Socket", name: str, message: Any) -> None:
    """
    broadcasts the message. It will send 2 messages: First the name with the send more flag,
        followed by the message.

    :param socket: The socket sending it.
    :param name: The name of the object, it will be the first part.
    :param messages: The data to send.
    """
    socket.send_string(name, flags=zmq.SNDMORE)
    socket.send(encode(message).encode("utf-8"))


class Broadcaster:
    """
    Mixin implementing the Broadcaster contract: an instrument that emits its
    own Broadcasts.

    The instrument calls :meth:`broadcast` with a
    :class:`~instrumentserver.blueprints.ParameterBroadcastBluePrint`; the
    Server registers itself as a sink with :meth:`add_broadcast_sink` when
    the instrument joins the Station. Used standalone (no sinks registered),
    :meth:`broadcast` is a no-op.

    Sinks are stored in a plain list: adding the same sink twice makes it
    receive every Broadcast twice. An exception raised inside one sink is
    logged and does not stop the remaining sinks.

    The annotations of the public methods are strings on purpose: the client
    builds proxy methods by exec-ing the blueprint's call signature string,
    and a rendered class annotation would reference a name the exec'd source
    cannot resolve. Keep new blueprint-carrying annotations quoted like these.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._broadcast_sinks: list[
            Callable[[ParameterBroadcastBluePrint], None]
        ] = []

    def add_broadcast_sink(
        self, fn: "Callable[[ParameterBroadcastBluePrint], None]"
    ) -> None:
        """
        Register ``fn`` as a sink that receives every Broadcast.

        :param fn: callable taking a ParameterBroadcastBluePrint.
        """
        self._broadcast_sinks.append(fn)

    def remove_broadcast_sink(
        self, fn: "Callable[[ParameterBroadcastBluePrint], None]"
    ) -> None:
        """
        Remove a sink that was registered with :meth:`add_broadcast_sink`.

        Removing a sink that is not registered does nothing.
        """
        if fn in self._broadcast_sinks:
            self._broadcast_sinks.remove(fn)

    def broadcast(self, bp: "ParameterBroadcastBluePrint") -> None:
        """
        Send a Broadcast to every registered sink.

        With no sinks registered this is a no-op. An exception raised inside
        one sink is logged and the remaining sinks still receive the
        Broadcast.
        """
        for sink in list(self._broadcast_sinks):
            try:
                sink(bp)
            except Exception:
                logger.exception(
                    f"Exception in broadcast sink {sink} while broadcasting "
                    f"'{bp.name}' / '{bp.action}'; continuing with the "
                    "remaining sinks."
                )


def recvMultipart(socket: "zmq.Socket") -> Tuple[str, Any]:
    """
    Recieves the broadcast from a broadcast message. It should consist of 2 parts:
     The first item is the name of the object sending it. Second part the message
    """
    messages = socket.recv_multipart()
    return messages[0].decode("utf-8"), decode(messages[1])
