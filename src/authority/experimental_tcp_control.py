"""Explicitly pumped, experimental cooperative TCP load-control channel.

No listener, engine or thread is started here. The caller exclusively owns the
coordinator, service, sockets and this object on one thread, and drives any
pause/save/resume operations separately. Accepted sockets are the connection
contexts. There is no peer authentication, encryption or native X4 integration.
"""
import json
import math
import select
import socket
import threading
import time

from .load_messages import MAX_MESSAGE, _pairs, _reject_constant
from .trusted_load_messages import decode_load_claim, encode_bound_offer
from .trusted_marker_load_session import TrustedMarkerLoadSession

_REQUEST = b'{"version":1,"kind":"offer_request"}\n'


def offer_request():
    """Return the sole initial/re-offer request frame."""
    return _REQUEST


def _request(raw):
    try:
        value = json.loads(raw.decode('utf-8'), object_pairs_hook=_pairs, parse_constant=_reject_constant)
    except (UnicodeError, json.JSONDecodeError, RecursionError) as error:
        raise ValueError('invalid request') from error
    if type(value) is not dict or set(value) != {'version', 'kind'} or type(value['version']) is not int or value['version'] != 1 or value['kind'] != 'offer_request':
        raise ValueError('invalid request')


class ExperimentalTCPControl:
    """One owner thread; every method and coordinator operation is serialized.

    `adopt` binds the actual connected socket to a new handle. `poll` is driven
    by the caller; it does not call WorldCoordinator.step. Before requesting an
    offer the caller must complete the world's required pause/save. A successful
    claim is only a trusted-client assertion, not proof that X4 consumed bytes.
    This prototype has only been exercised on loopback; it is not a complete
    Internet protocol or a decision about the eventual transport policy.
    """
    def __init__(self, session, *, enabled=False, idle_timeout=30, max_peers=8):
        if enabled is not True or type(session) is not TrustedMarkerLoadSession:
            raise ValueError('explicitly enabled trusted session required')
        if type(idle_timeout) not in (int, float) or not math.isfinite(idle_timeout) or not 0 < idle_timeout <= 300:
            raise ValueError('invalid idle timeout')
        if type(max_peers) is not int or not 1 <= max_peers <= 64:
            raise ValueError('invalid peer limit')
        self._session = session
        self._timeout = float(idle_timeout)
        self._limit = max_peers
        self._peers = {}
        self._thread = threading.get_ident()
        self._failed = False
        self._closed = False

    def _owner(self):
        if threading.get_ident() != self._thread:
            raise RuntimeError('exclusive owner thread required')
        if self._failed or self._closed:
            raise RuntimeError('control channel unavailable')

    def _fatal(self, error):
        self._failed = True
        for conn in tuple(self._peers):
            try: conn.close()
            except BaseException: pass
        self._peers.clear()
        raise RuntimeError('control channel faulted; fence coordinator and service') from error

    def adopt(self, conn):
        """Adopt one connected socket; caller retains listener and transport policy."""
        self._owner()
        if (type(conn) is not socket.socket or conn.family != socket.AF_INET or conn.proto not in (0, socket.IPPROTO_TCP) or
                conn.getsockopt(socket.SOL_SOCKET, socket.SO_TYPE) != socket.SOCK_STREAM):
            raise ValueError('connected IPv4 TCP stream socket required')
        if conn in self._peers or len(self._peers) >= self._limit:
            raise ValueError('duplicate connection or peer limit')
        conn.getpeername()  # reject unconnected/closed sockets before mutating session
        conn.setblocking(False)
        if not self._live_socket(conn):
            raise ValueError('connection already closed')
        try:
            handle = self._session.attach(conn)
            self._peers[conn] = {'handle': handle, 'in': b'', 'out': b'', 'stage': 'attached',
                                 'deadline': time.monotonic() + self._timeout}
        except BaseException as error:
            # attach may have succeeded even if control was interrupted
            # before the new connection could be recorded here.
            try: conn.close()
            except BaseException: pass
            self._fatal(error)
        return handle

    def _drop(self, conn):
        try:
            self._peers.pop(conn)
            self._session.disconnect(conn)
            conn.close()
        except BaseException as error:
            try:
                conn.close()
            except BaseException:
                pass
            finally: self._fatal(error)

    @staticmethod
    def _live_socket(conn):
        # A peer which has already closed its write side cannot submit an
        # admission claim. This is point-in-time, not transport authentication.
        try:
            if select.select([conn], [], [], 0)[0]:
                try: return conn.recv(1, socket.MSG_PEEK) != b''
                except BlockingIOError: return True
            return True
        except (OSError, ValueError):
            return False

    def _current_socket(self, conn, peer):
        return (self._peers.get(conn) is peer and time.monotonic() < peer['deadline']
                and self._live_socket(conn))

    def _offer_ready(self):
        world = self._session._world
        state = world.session
        return (state.state == 'paused' and state.pending is None and not state.save_required
                and state.baseline_id is not None and world._baseline is not None
                and world._baseline[0] == state.baseline_id)

    def _frame(self, conn, peer, raw):
        try:
            if peer['stage'] in ('attached', 'offered'):
                # A re-offer withdraws the old generation before issuing a new one.
                try: _request(raw)
                except ValueError:
                    if peer['stage'] != 'offered': raise
                else:
                    if not self._offer_ready():
                        peer['out'] += b'{"version":1,"kind":"not_ready"}\n'
                        return
                    bound = self._session.begin(conn)
                    if not self._current_socket(conn, peer):
                        self._drop(conn)
                        return
                    peer['out'] += encode_bound_offer(bound) + b'\n'
                    peer['stage'] = 'offered'
                    return
            if peer['stage'] != 'offered':
                raise ValueError('unexpected control message')
            claim = decode_load_claim(raw)
            outcome = self._session.accept(conn, claim, pre_accept=lambda: self._current_socket(conn, peer))
            if not self._current_socket(conn, peer):
                self._drop(conn)
                return
            reply = {'version': 1, 'kind': 'accepted', 'attempt_id': outcome.attempt_id}
            peer['out'] += json.dumps(reply, separators=(',', ':'), sort_keys=True).encode('ascii') + b'\n'
            peer['stage'] = 'admitted'
        except ValueError as error:
            if self._session._failed or self._session._inner._failed:
                self._fatal(error)
            self._drop(conn)
        except BaseException as error:
            self._fatal(error)

    def poll(self, timeout=0):
        """Handle bounded socket I/O and idle expiry once on the owner thread."""
        self._owner()
        if type(timeout) not in (int, float) or not math.isfinite(timeout) or not 0 <= timeout <= 1:
            raise ValueError('invalid poll timeout')
        now = time.monotonic()
        for conn, peer in tuple(self._peers.items()):
            if peer['deadline'] is not None and now >= peer['deadline']:
                self._drop(conn)
        if not self._peers:
            return
        sockets = tuple(self._peers)
        deadlines = [p['deadline'] for p in self._peers.values() if p['deadline'] is not None]
        wait = min(timeout, max(0, min(deadlines) - time.monotonic())) if deadlines else timeout
        try:
            readable, writable, exceptional = select.select(sockets, [c for c in sockets if self._peers[c]['out']], sockets, wait)
        except (OSError, ValueError) as error:
            self._fatal(error)
        now = time.monotonic()
        for conn, peer in tuple(self._peers.items()):
            if peer['deadline'] is not None and now >= peer['deadline']:
                self._drop(conn)
        for conn in exceptional:
            if conn in self._peers: self._drop(conn)
        for conn in readable:
            if conn not in self._peers: continue
            try: chunk = conn.recv(MAX_MESSAGE + 1)
            except BlockingIOError: continue
            except OSError:
                self._drop(conn); continue
            if not chunk:
                self._drop(conn); continue
            peer = self._peers[conn]
            if peer['out']:
                self._drop(conn); continue
            peer['in'] += chunk
            # Process at most one message per peer per poll; avoid unbounded
            # buffering and reject pipelined input rather than mixing attempts.
            if b'\n' in peer['in']:
                raw, tail = peer['in'].split(b'\n', 1)
                if len(raw) > MAX_MESSAGE or tail:
                    self._drop(conn); continue
                peer['in'] = b''
                peer['deadline'] = time.monotonic() + self._timeout
                self._frame(conn, peer, raw)
            elif len(peer['in']) > MAX_MESSAGE:
                self._drop(conn)
        for conn in writable:
            if conn not in self._peers: continue
            peer = self._peers[conn]
            try: sent = conn.send(peer['out'])
            except BlockingIOError: continue
            except OSError:
                self._drop(conn); continue
            if sent <= 0: self._drop(conn)
            else:
                peer['out'] = peer['out'][sent:]
                if not peer['out'] and peer['stage'] == 'admitted':
                    peer['deadline'] = None

    def ready_for_resume(self):
        """Point-in-time output-drain and peer check; caller must honor it.

        True means no tracked peer has pending output or unread input and no
        EOF was observed. It does not establish remote receipt or future liveness.
        The coordinator still decides whether a resume is valid.
        """
        self._owner()
        ready = True
        for conn, peer in tuple(self._peers.items()):
            if peer['deadline'] is not None and time.monotonic() >= peer['deadline']:
                self._drop(conn)
                ready = False
                continue
            try:
                readable, _, exceptional = select.select([conn], [], [conn], 0)
                if exceptional:
                    self._drop(conn)
                    ready = False
                    continue
                if readable:
                    try: data = conn.recv(1, socket.MSG_PEEK)
                    except BlockingIOError: data = None
                    if data == b'':
                        self._drop(conn)
                    ready = False
                if peer['in'] or peer['out']:
                    ready = False
            except (OSError, ValueError):
                self._drop(conn)
                ready = False
        return ready

    def close(self):
        """Disconnect all adopted sockets, retaining no listener or thread."""
        self._owner()
        try:
            for conn in tuple(self._peers): self._drop(conn)
        finally:
            self._closed = True
