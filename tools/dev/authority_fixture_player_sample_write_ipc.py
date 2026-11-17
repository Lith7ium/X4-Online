"""One correlated fixture-player XYZ write through an owned local X4 socket.

The supervisor owns the private server process, profile, grant and cleanup. A
successful response is a local immediate readback assertion, not continuous
motion, frame equivalence, a velocity write, or gameplay evidence. Once a send
is attempted its game-side effect is uncertain until independently confirmed;
this owner never retries a write.
"""
import copy
import json
import math
import re
import secrets
import select
import socket
import threading
import time

from authority.experimental_participant_job_ipc import _LOCK, _OWNERS
from authority.experimental_tcp_client_authority_motion import grant_value
from authority.experimental_tcp_motion import motion_digest, motion_value
from authority_tcp_job_client_live import socket_owner
from authority_tcp_native_worker import check_process

_TOKEN = re.compile(r'[0-9a-f]{32}\Z')
_NUMBER = re.compile(r'[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?\Z')
_MAX_PACKET = 768


class FixturePlayerSampleWriteIPC:
    """Own one bound UDP socket and allow at most one guarded XYZ dispatch."""

    def __init__(self, sock, *, enabled=False, lease, attempt, grant, process,
                 guard, grant_guard, timeout=20):
        if (enabled is not True or type(sock) is not socket.socket or
                sock.family != socket.AF_INET or
                sock.getsockopt(socket.SOL_SOCKET, socket.SO_TYPE) != socket.SOCK_DGRAM or
                sock.getsockname()[0] != '127.0.0.1' or not sock.getsockname()[1] or
                any(type(value) is not str or not _TOKEN.fullmatch(value) for value in (lease, attempt)) or
                type(process) is not dict or not callable(guard) or not callable(grant_guard) or
                type(timeout) not in (int, float) or not math.isfinite(timeout) or not 0 < timeout <= 120):
            raise ValueError('invalid fixture player write context')
        checked_grant = grant_value(grant)
        tokens = (lease, attempt, checked_grant['epoch'], checked_grant['generation'],
                  checked_grant['token'], checked_grant['incarnation'])
        if checked_grant['index'] not in (3, 4) or len(set(tokens)) != len(tokens):
            raise ValueError('fixture player write grant or tokens differ')
        try:
            sock.getpeername()
        except OSError:
            pass
        else:
            raise ValueError('unconnected bound fixture UDP socket required')
        identity = dict(process)
        check_process(identity)
        with _LOCK:
            if sock in _OWNERS:
                raise ValueError('fixture UDP socket is already owned')
            sock.setblocking(False)
            _OWNERS[sock] = True
        self._sock = sock
        self._local = sock.getsockname()
        self._peer = None
        self._lease, self._attempt = lease, attempt
        self._grant = checked_grant
        self._grant_wire = json.dumps(checked_grant, sort_keys=True, separators=(',', ':'), allow_nan=False)
        self._process = identity
        self._guard, self._grant_guard = guard, grant_guard
        self._timeout = float(timeout)
        self._thread = threading.get_ident()
        self._state = 'new'
        self._write_attempted = False
        self._write_confirmed = False

    @property
    def state(self):
        return self._state

    @property
    def write_attempted(self):
        """True means dispatch began; it does not prove that X4 received it."""
        return self._write_attempted

    @property
    def write_confirmed(self):
        """True means the correlated local immediate-readback response passed."""
        return self._write_confirmed

    def _fail(self):
        self._state = 'failed'
        with _LOCK:
            _OWNERS.pop(self._sock, None)
        self._sock.close()

    def _check(self, deadline, phase):
        original_socket, original_guard, original_grant_guard = self._sock, self._guard, self._grant_guard
        context = (self._local, self._peer, self._lease, self._attempt, copy.deepcopy(self._grant),
                   copy.deepcopy(self._process), self._timeout, self._thread,
                   self._write_attempted, self._write_confirmed, self._grant_wire)

        def peer_unchanged():
            try:
                actual_peer = self._sock.getpeername()
            except OSError:
                return self._peer is None
            return self._peer is not None and actual_peer == self._peer

        def unchanged():
            current = (self._local, self._peer, self._lease, self._attempt, self._grant,
                       self._process, self._timeout, self._thread,
                       self._write_attempted, self._write_confirmed, self._grant_wire)
            return (self._sock is original_socket and self._guard is original_guard and
                    self._grant_guard is original_grant_guard and current == context and
                    all(type(left) is type(right) for left, right in zip(current, context)) and
                    json.dumps(self._grant, sort_keys=True, separators=(',', ':'), allow_nan=False) == self._grant_wire and
                    self._state == phase and threading.get_ident() == self._thread and
                    time.monotonic() < deadline and self._sock.getsockname() == self._local and
                    peer_unchanged())

        if not unchanged():
            raise RuntimeError('fixture write context or deadline changed')
        check_process(copy.deepcopy(self._process))
        if not unchanged() or self._guard() is not True or not unchanged():
            raise RuntimeError('fixture write process guard failed')
        candidate = copy.deepcopy(self._grant)
        if (self._grant_guard(candidate) is not True or
                json.dumps(candidate, sort_keys=True, separators=(',', ':'), allow_nan=False) != self._grant_wire or
                not unchanged()):
            raise RuntimeError('fixture write grant guard failed')
        if self._peer is not None:
            valid = socket_owner(self._peer, self._local, copy.deepcopy(self._process))
            if valid is not True or not unchanged():
                raise RuntimeError('fixture write peer ownership changed')
        check_process(copy.deepcopy(self._process))
        if not unchanged() or self._guard() is not True or not unchanged():
            raise RuntimeError('fixture write process changed')
        candidate = copy.deepcopy(self._grant)
        if (self._grant_guard(candidate) is not True or
                json.dumps(candidate, sort_keys=True, separators=(',', ':'), allow_nan=False) != self._grant_wire or
                not unchanged()):
            raise RuntimeError('fixture write grant changed')
        if self._peer is not None:
            valid = socket_owner(self._peer, self._local, copy.deepcopy(self._process))
            if valid is not True or not unchanged():
                raise RuntimeError('fixture write peer changed after grant check')

    def _quiet(self, deadline, phase):
        self._check(deadline, phase)
        readable, _, exceptional = select.select([self._sock], [], [self._sock], 0)
        if readable or exceptional:
            raise RuntimeError('unexpected queued fixture write packet')
        self._check(deadline, phase)

    def _receive(self, deadline, phase, *, unconnected=False):
        while True:
            self._check(deadline, phase)
            readable, _, exceptional = select.select([self._sock], [], [self._sock],
                min(.1, max(0, deadline - time.monotonic())))
            self._check(deadline, phase)
            if exceptional:
                raise RuntimeError('fixture write socket failed')
            if readable:
                if unconnected:
                    packet, peer = self._sock.recvfrom(_MAX_PACKET + 1)
                else:
                    packet, peer = self._sock.recv(_MAX_PACKET + 1), self._peer
                if not packet or len(packet) > _MAX_PACKET:
                    raise ValueError('invalid fixture write packet')
                self._check(deadline, phase)
                return packet, peer

    def wait_ready(self):
        if self._state != 'new' or threading.get_ident() != self._thread:
            self._fail()
            raise RuntimeError('fixture write readiness unavailable')
        self._state = 'binding'
        deadline = time.monotonic() + self._timeout
        try:
            packet, peer = self._receive(deadline, 'binding', unconnected=True)
            grant = self._grant
            expected = '|'.join(('R', self._lease, self._attempt, 'READY', grant['epoch'],
                                 grant['generation'], str(grant['index']), grant['sector_macro'])).encode('ascii')
            if packet != expected or peer[0] != '127.0.0.1' or not peer[1]:
                raise ValueError('foreign fixture write READY')
            self._check(deadline, 'binding')
            if socket_owner(peer, self._local, copy.deepcopy(self._process)) is not True:
                raise RuntimeError('fixture write READY peer is not owned')
            self._check(deadline, 'binding')
            self._sock.connect(peer)
            self._peer = peer
            self._quiet(deadline, 'binding')
            self._state = 'ready'
            return True
        except BaseException:
            self._fail()
            raise

    def apply_once(self, sample):
        if self._state != 'ready' or threading.get_ident() != self._thread:
            self._fail()
            raise RuntimeError('fixture write unavailable')
        self._state = 'writing'
        deadline = time.monotonic() + self._timeout
        try:
            value = motion_value(sample)
            grant = self._grant
            if (value['version'] != 2 or value['epoch'] != grant['epoch'] or
                    value['generation'] != grant['generation'] or value['index'] != grant['index'] or
                    value['sector_macro'] != grant['sector_macro']):
                raise ValueError('fixture SAMPLE2 differs from the grant')
            digest = motion_digest(value)
            request = secrets.token_hex(16)
            if request in (self._lease, self._attempt, grant['epoch'], grant['generation'],
                           grant['token'], grant['incarnation']):
                raise RuntimeError('fixture write request token reused')
            identity = [request, grant['epoch'], grant['generation'], str(grant['index']),
                        str(value['sequence']), grant['sector_macro'], digest]
            target = [value[axis] for axis in ('x', 'y', 'z')]
            payload = '|'.join(['P', self._lease, self._attempt, 'WRITE', *identity,
                                *(format(number, '.17g') for number in target)]).encode('ascii')
            if len(payload) > _MAX_PACKET:
                raise ValueError('fixture write request too large')
            self._quiet(deadline, 'writing')
            self._write_attempted = True
            if self._sock.send(payload) != len(payload):
                raise RuntimeError('fixture write dispatch failed')
            self._check(deadline, 'writing')
            packet, _ = self._receive(deadline, 'writing')
            try:
                fields = packet.decode('ascii').split('|')
            except UnicodeError:
                raise ValueError('invalid fixture write encoding') from None
            prefix = ['R', self._lease, self._attempt, 'RESULT', *identity]
            if len(fields) != len(prefix) + 6 or fields[:len(prefix)] != prefix:
                raise ValueError('fixture write result correlation differs')
            values = fields[len(prefix):]
            if any(len(item) > 32 or not _NUMBER.fullmatch(item) for item in values):
                raise ValueError('invalid fixture write result coordinates')
            numbers = [float(item) for item in values]
            if any(not math.isfinite(number) or abs(number) > 1e7 for number in numbers):
                raise ValueError('fixture write result coordinates out of bounds')
            before, after = numbers[:3], numbers[3:]
            initial_distance = math.dist(before, target)
            if not math.isfinite(initial_distance) or not 1 <= initial_distance <= 50:
                raise ValueError('fixture target separation is outside the allowed range')
            error = math.dist(after, target)
            if not math.isfinite(error) or error > .5:
                raise ValueError('fixture immediate readback differs from target')
            self._quiet(deadline, 'writing')
            self._write_confirmed = True
            self._state = 'done'
            return {'registry_index': grant['index'], 'sector_macro': grant['sector_macro'],
                    'source_sequence': value['sequence'], 'sample_sha256': digest,
                    'target': target, 'before': before, 'after': after,
                    'initial_distance': initial_distance, 'target_error': error,
                    'position_only': True, 'sustained_motion_proven': False}
        except BaseException:
            self._fail()
            raise

    def close(self):
        if threading.get_ident() != self._thread:
            raise RuntimeError('fixture write owner thread changed')
        if self._state == 'closed':
            return
        if self._state not in ('new', 'ready', 'done', 'failed'):
            self._fail()
            raise RuntimeError('fixture write cannot close during an operation')
        with _LOCK:
            _OWNERS.pop(self._sock, None)
        self._sock.close()
        self._state = 'closed'
