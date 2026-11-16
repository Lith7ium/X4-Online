"""Opt-in local UDP application bridge for an admitted TCP participant.

The caller owns X4, the process/profile guard and the participant TCP pump.
The Lua owner reports APPLIED only after its correlated MD and FFI readbacks.
Neither local UDP tokens nor the echoed digest authenticate another process.
"""
import math
import re
import secrets
import select
import socket
import threading
import time
import weakref

from .experimental_tcp_job_delivery import job_digest, job_event

_TOKEN = re.compile(r'[0-9a-f]{32}\Z')
_MAX_PACKET = 768
_OWNERS = weakref.WeakKeyDictionary()
_LOCK = threading.Lock()


class ExperimentalParticipantJobIPC:
    """Single-thread, single X4-owner IPC; failures permanently fence the bridge.

    Before starting X4, pass an exclusively owned, bound, unconnected loopback
    UDP socket. `wait_ready` pins the one peer only after the caller's explicit
    process/socket ownership validator accepts its address. Connect the bridge
    itself as `ExperimentalTCPParticipantClient(..., apply_job=bridge)`.
    Its synchronous call blocks that TCP pump while the separate X4 onUpdate
    owner executes asynchronously. The supervisor must allocate a strictly
    smaller IPC timeout than the remaining TCP operation deadline.
    """
    def __init__(self, sock, *, enabled=False, lease, attempt, epoch, generation,
                 guard, validate_peer, timeout=30):
        if (enabled is not True or type(sock) is not socket.socket or
            sock.family != socket.AF_INET or
            sock.getsockopt(socket.SOL_SOCKET, socket.SO_TYPE) != socket.SOCK_DGRAM or
            sock.getsockname()[0] != '127.0.0.1' or not sock.getsockname()[1] or
            any(type(v) is not str or not _TOKEN.fullmatch(v) for v in (lease, attempt, epoch, generation)) or
            len({lease, attempt, epoch, generation}) != 4 or
            not callable(guard) or not callable(validate_peer) or
            type(timeout) not in (int, float) or not math.isfinite(timeout) or not 0 < timeout <= 300):
            raise ValueError('enabled bound loopback UDP socket and context required')
        try: sock.getpeername()
        except OSError: pass
        else: raise ValueError('UDP socket must initially be unconnected')
        with _LOCK:
            if sock in _OWNERS: raise ValueError('UDP socket already owned')
            sock.setblocking(False); _OWNERS[sock] = True
        self._sock, self._lease, self._attempt = sock, lease, attempt
        self._epoch, self._generation = epoch, generation
        self._guard, self._validate_peer, self._timeout = guard, validate_peer, float(timeout)
        self._owner, self._state = threading.get_ident(), 'new'
        self._nonce = secrets.token_hex(8)
        self._last_sequence = None
        self._peer = None

    @property
    def state(self): return self._state

    def _fail(self):
        self._state = 'failed'
        try: self._sock.close()
        except OSError: pass

    def _check(self, deadline, state):
        if threading.get_ident() != self._owner or self._state != state or time.monotonic() >= deadline:
            raise RuntimeError('participant IPC unavailable')
        valid = self._guard()
        if (valid is not True or self._state != state or threading.get_ident() != self._owner or
            time.monotonic() >= deadline):
            raise RuntimeError('participant IPC process guard or deadline failed')
        if self._peer is not None:
            valid = self._validate_peer(self._peer)
        if (valid is not True or self._state != state or threading.get_ident() != self._owner or
            time.monotonic() >= deadline):
            raise RuntimeError('participant IPC process guard or deadline failed')

    def _receive(self, deadline, state, unconnected=False):
        while True:
            self._check(deadline, state)
            ready, _, exceptional = select.select([self._sock], [], [self._sock],
                                                    min(.1, max(0, deadline-time.monotonic())))
            self._check(deadline, state)
            if exceptional: raise RuntimeError('participant IPC socket error')
            if ready:
                if unconnected: data, peer = self._sock.recvfrom(_MAX_PACKET+1)
                else: data, peer = self._sock.recv(_MAX_PACKET+1), self._peer
                if not data or len(data) > _MAX_PACKET: raise ValueError('invalid IPC packet size')
                self._check(deadline, state)
                return data, peer

    def _quiet(self, deadline, state):
        self._check(deadline, state)
        readable, _, exceptional = select.select([self._sock], [], [self._sock], 0)
        if readable or exceptional: raise RuntimeError('unexpected queued participant IPC packet')
        self._check(deadline, state)

    def wait_ready(self):
        if threading.get_ident() != self._owner or self._state != 'new':
            self._fail(); raise RuntimeError('participant IPC invalid ready state')
        self._state = 'binding'; deadline = time.monotonic()+self._timeout
        try:
            data, peer = self._receive(deadline, 'binding', unconnected=True)
            expected = f'X|{self._lease}|{self._attempt}|READY|{self._epoch}|{self._generation}'.encode('ascii')
            if data != expected or peer[0] != '127.0.0.1' or not peer[1]:
                raise ValueError('foreign participant ready')
            self._check(deadline, 'binding')
            valid = self._validate_peer(peer)
            self._check(deadline, 'binding')
            if valid is not True: raise RuntimeError('X4 UDP peer ownership unconfirmed')
            self._sock.connect(peer); self._peer = peer
            self._quiet(deadline, 'binding')
            self._state = 'ready'
            return True
        except BaseException:
            self._fail(); raise

    def __call__(self, raw_event):
        if threading.get_ident() != self._owner or self._state != 'ready':
            self._fail(); raise RuntimeError('participant IPC reentrant or unavailable')
        self._state = 'applying'; deadline = time.monotonic()+self._timeout
        try:
            event = job_event(raw_event)
            if (event['epoch'] != self._epoch or event['generation'] != self._generation or
                self._last_sequence is not None and event['sequence'] != self._last_sequence+1):
                raise ValueError('foreign or stale job event')
            d = event['descriptor']
            if any(abs(d[k]) > 10000000 for k in ('x','y','z')):
                raise ValueError('coordinates outside experimental receiver limits')
            request = self._nonce + format(event['sequence'], '016x')
            digest = job_digest(event)
            identity = [request, event['epoch'], event['generation'], str(event['sequence']), str(event['index']), digest]
            payload = '|'.join(['P', self._lease, self._attempt, 'APPLY', *identity,
                                d['macro'], d['faction'], d['sector_macro'],
                                *(format(d[k], '.17g') for k in ('x','y','z'))]).encode('ascii')
            if len(payload) > _MAX_PACKET: raise ValueError('IPC packet too large')
            self._quiet(deadline, 'applying')
            if self._sock.send(payload) != len(payload): raise RuntimeError('participant IPC send failed')
            self._check(deadline, 'applying')
            data, _ = self._receive(deadline, 'applying')
            expected = '|'.join(['X', self._lease, self._attempt, 'APPLIED', *identity]).encode('ascii')
            if data != expected: raise ValueError('participant IPC response mismatch')
            self._quiet(deadline, 'applying')
            self._last_sequence = event['sequence']; self._state = 'ready'
            return True
        except BaseException:
            self._fail(); raise

    def close(self):
        if threading.get_ident() != self._owner or self._state not in ('new', 'ready'):
            self._fail(); raise RuntimeError('participant IPC unavailable')
        self._state = 'closed'
        with _LOCK: _OWNERS.pop(self._sock, None)
        self._sock.close()
