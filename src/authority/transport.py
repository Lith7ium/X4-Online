"""Experimental loopback transport for the ship-state registry.

This process is a state exchange, not the X4 simulation. One connected engine
adapter is the server and can delegate individual ships to connected clients.
No automatic takeover is attempted on disconnect: the engine must reconcile
the last accepted state before it explicitly changes ownership.

Create and update accept an optional ``velocity`` object with exactly x/y/z,
in the position's caller-defined frame. Omitting it or sending null means
unknown; it does not preserve an earlier vector. Responses omit unknown
velocity for position-only compatibility. This does not define X4 units,
velocity sampling, game application, Internet transport or clock semantics.
"""

from dataclasses import asdict
import json
import re
import socketserver
import threading

from .ship_state import Position, ShipRegistry, Velocity

MAX_LINE = 16384
MAX_PAGE = 128
MAX_PEERS = 9
PEER_NAME = re.compile(r"[A-Za-z0-9_-]{1,48}\Z")


def _fields(value, expected):
    if not isinstance(value, dict) or set(value) != set(expected):
        raise ValueError("invalid message fields")


def _position(value):
    _fields(value, ("sector", "x", "y", "z"))
    return Position(**value)


def _motion_fields(value, required):
    """Accept legacy position-only or complete position-plus-velocity state."""
    if not isinstance(value, dict) or set(value) not in (set(required), set(required) | {'velocity'}):
        raise ValueError('invalid message fields')


def _velocity(value):
    if value is None:
        return None
    _fields(value, ('x', 'y', 'z'))
    return Velocity(**value)


def _wire_state(state):
    """Omit unknown velocity to preserve position-only response shape."""
    value = asdict(state)
    if value['velocity'] is None:
        del value['velocity']
    return value


class ShipExchange(socketserver.ThreadingTCPServer):
    """Temporary local test server; a new instance always needs a new epoch."""

    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, address, world_epoch):
        if address[0] != "127.0.0.1":
            raise ValueError("experimental server is restricted to IPv4 loopback")
        self.registry = ShipRegistry(world_epoch)
        self.lock = threading.RLock()
        self.peers = {}
        self.revision = 0
        self.server_departed = False
        super().__init__(address, _Handler)

    def join(self, peer, handler):
        if not isinstance(peer, str) or not PEER_NAME.fullmatch(peer):
            raise ValueError("invalid peer name")
        with self.lock:
            if self.server_departed:
                raise ValueError("server engine disconnected; start a new world epoch")
            if peer in self.peers:
                raise ValueError("peer already connected")
            if len(self.peers) >= MAX_PEERS:
                raise ValueError("peer limit reached")
            self.peers[peer] = handler

    def leave(self, peer, handler):
        with self.lock:
            if self.peers.get(peer) is handler:
                del self.peers[peer]
                if peer == "server":
                    self.server_departed = True
                else:
                    # Fence the old writer, but do not pretend the game has
                    # reconciled the accepted position into its simulation.
                    for state in self.registry.snapshot():
                        if state.owner == peer:
                            self.registry.assign(state.ship_id, state.generation,
                                                 state.authority_epoch, "offline:" + peer)
                            self.revision += 1

    def request(self, peer, handler, message):
        if not isinstance(message, dict) or not isinstance(message.get("op"), str):
            raise ValueError("invalid request")
        op = message["op"]
        with self.lock:
            if self.peers.get(peer) is not handler:
                raise ValueError("peer not connected")
            if op == "snapshot":
                _fields(message, ("op", "offset", "revision"))
                offset, revision = message["offset"], message["revision"]
                if type(offset) is not int or offset < 0:
                    raise ValueError("invalid offset")
                if offset == 0:
                    if revision is not None:
                        raise ValueError("first page requires null revision")
                    handler.snapshot = (self.revision, self.registry.snapshot(),
                                        "server" in self.peers and not self.server_departed)
                elif (type(revision) is not int or handler.snapshot is None or
                      revision != handler.snapshot[0]):
                    raise ValueError("snapshot expired; restart at offset zero")
                snapshot_revision, rows, captured_online = handler.snapshot
                if offset > len(rows):
                    raise ValueError("offset exceeds snapshot")
                page = rows[offset:offset + MAX_PAGE]
                next_offset = offset + len(page)
                return {"revision": snapshot_revision, "world_epoch": self.registry.world_epoch,
                        "server_online_at_capture": captured_online,
                        "server_online": "server" in self.peers and not self.server_departed,
                        "ships": [_wire_state(row) for row in page],
                        "next_offset": next_offset if next_offset < len(rows) else None}
            if self.server_departed or "server" not in self.peers:
                raise ValueError("server engine adapter not connected")
            if message.get("world_epoch") != self.registry.world_epoch:
                raise ValueError("wrong world epoch")
            if op == "update":
                _motion_fields(message, ("op", "world_epoch", "ship_id", "generation",
                                         "authority_epoch", "sequence", "position"))
                result = self.registry.update(message["world_epoch"], message["ship_id"],
                                              message["generation"], message["authority_epoch"],
                                              None if peer == "server" else peer,
                                              message["sequence"], _position(message["position"]),
                                              _velocity(message.get('velocity')))
            else:
                if peer != "server":
                    raise ValueError("only the server engine may change ownership or lifecycle")
                if op == "create":
                    _motion_fields(message, ("op", "world_epoch", "ship_id", "generation", "position"))
                    result = self.registry.create(message["ship_id"], message["generation"],
                                                  _position(message["position"]), _velocity(message.get('velocity')))
                elif op == "assign":
                    _fields(message, ("op", "world_epoch", "ship_id", "generation", "authority_epoch", "owner"))
                    owner = message["owner"]
                    if owner is not None and (owner == "server" or owner not in self.peers):
                        raise ValueError("new owner is not a connected client")
                    result = self.registry.assign(message["ship_id"], message["generation"],
                                                  message["authority_epoch"], owner)
                elif op == "remove":
                    _fields(message, ("op", "world_epoch", "ship_id", "generation", "authority_epoch"))
                    result = self.registry.remove(message["ship_id"], message["generation"],
                                                  message["authority_epoch"])
                else:
                    raise ValueError("unknown operation")
            self.revision += 1
            return {"revision": self.revision, "ship": _wire_state(result) if result is not None else None}


class _Handler(socketserver.StreamRequestHandler):
    def handle(self):
        self.request.settimeout(30)
        self.snapshot = None
        peer = None
        try:
            while True:
                raw = self.rfile.readline(MAX_LINE + 1)
                if not raw:
                    return
                if len(raw) > MAX_LINE or not raw.endswith(b"\n"):
                    return
                try:
                    message = json.loads(raw, parse_constant=lambda _: (_ for _ in ()).throw(ValueError("non-finite number")))
                    if peer is None:
                        _fields(message, ("op", "peer"))
                        if message["op"] != "hello":
                            raise ValueError("hello required")
                        candidate = message["peer"]
                        self.server.join(candidate, self)
                        peer = candidate
                        value = {"world_epoch": self.server.registry.world_epoch}
                    else:
                        value = self.server.request(peer, self, message)
                    reply = {"ok": True, "value": value}
                except (ValueError, TypeError, KeyError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                    reply = {"ok": False, "error": str(exc)}
                encoded = json.dumps(reply, allow_nan=False, separators=(",", ":")).encode("utf-8") + b"\n"
                self.wfile.write(encoded)
                self.wfile.flush()
        except (ConnectionError, OSError):
            pass
        finally:
            if peer is not None:
                self.server.leave(peer, self)
