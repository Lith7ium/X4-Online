"""Pumpable, loopback-only experiment for cooperative participant control.

The caller owns this connected socket after consuming the load-accepted frame,
the X4 process and the injected synchronous controller. A controller result is
a local assertion; this module does not establish process or peer identity.
"""
import json
import math
import re
import select
import socket
import threading
import time

from .load_messages import MAX_INTEGER, MAX_MESSAGE, _pairs, _reject_constant


class ExperimentalTCPParticipantClient:
    """Accept one command at a time, and reply only after local confirmation.

    The controller must bound its own synchronous pause/resume calls. This
    adapter checks its deadline after a call but cannot interrupt that call.
    """
    def __init__(self, conn, controller, *, enabled=False, epoch, handle, timeout=30):
        if (enabled is not True or type(conn) is not socket.socket or conn.family != socket.AF_INET or
                conn.proto not in (0, socket.IPPROTO_TCP) or
                conn.getsockopt(socket.SOL_SOCKET, socket.SO_TYPE) != socket.SOCK_STREAM or
                type(epoch) is not str or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', epoch) or
                type(handle) is not int or not 1 <= handle <= MAX_INTEGER or
                type(timeout) not in (int, float) or not math.isfinite(timeout) or not 0 < timeout <= 300 or
                not callable(getattr(controller, 'pause', None)) or
                not callable(getattr(controller, 'resume', None))):
            raise ValueError('enabled client, controller and bounded configuration required')
        if conn.getpeername()[0] != '127.0.0.1':
            raise ValueError('experimental client requires loopback peer')
        conn.setblocking(False)
        self._conn, self._controller, self._epoch, self._handle = conn, controller, epoch, handle
        self._timeout = float(timeout)
        self._thread = threading.get_ident()
        self._in = self._out = b''
        self._deadline = None
        self._last = 0
        self._failed = self._closed = self._busy = False

    def _fault(self):
        self._failed = True
        try: self._conn.close()
        except BaseException: pass

    def _owner(self):
        if threading.get_ident() != self._thread:
            raise RuntimeError('exclusive owner thread required')
        if self._failed or self._closed:
            raise RuntimeError('participant client unavailable; fence local controller')
        if self._busy:
            self._fault()
            raise RuntimeError('reentrant participant client access')

    def _within(self):
        if self._failed or self._closed:
            raise RuntimeError('participant client changed during operation')
        if self._deadline is not None and time.monotonic() >= self._deadline:
            raise TimeoutError('participant operation deadline exceeded')

    def _quiet(self):
        readable, _, exceptional = select.select([self._conn], [], [self._conn], 0)
        if readable or exceptional:
            raise RuntimeError('unexpected input or disconnect during participant operation')
        self._within()

    def _command(self, raw):
        try:
            command = json.loads(raw.decode('utf-8'), object_pairs_hook=_pairs, parse_constant=_reject_constant)
        except (UnicodeError, json.JSONDecodeError, RecursionError) as error:
            raise ValueError('invalid participant command') from error
        fields = {'version', 'kind', 'epoch', 'connection_handle', 'request_id', 'operation'}
        if (type(command) is not dict or set(command) != fields or
                type(command['version']) is not int or command['version'] != 1 or
                command['kind'] != 'participant_command' or command['epoch'] != self._epoch or
                type(command['connection_handle']) is not int or command['connection_handle'] != self._handle or
                type(command['request_id']) is not int or not self._last < command['request_id'] <= MAX_INTEGER or
                command['operation'] not in ('pause', 'resume')):
            raise ValueError('unexpected or stale participant command')
        self._quiet()
        self._last = command['request_id']  # never dispatch it twice
        confirmed = getattr(self._controller, command['operation'])((self._handle,))
        self._within()
        self._quiet()
        if confirmed is not True:
            raise RuntimeError('local participant state not confirmed')
        reply = dict(command, kind='participant_receipt', status='confirmed')
        self._out = json.dumps(reply, sort_keys=True, separators=(',', ':')).encode('utf-8') + b'\n'

    def poll(self, timeout=0):
        """Pump bounded I/O once; True means a receipt was sent to the socket."""
        self._owner()
        if type(timeout) not in (int, float) or not math.isfinite(timeout) or not 0 <= timeout <= 1:
            raise ValueError('invalid poll timeout')
        self._busy = True
        try:
            self._within()
            wait = timeout if self._deadline is None else min(timeout, max(0, self._deadline-time.monotonic()))
            readable, writable, exceptional = select.select([self._conn], [self._conn] if self._out else [], [self._conn], wait)
            self._within()
            if exceptional: raise RuntimeError('participant socket exception')
            if readable:
                if self._out: raise RuntimeError('pipelined participant command')
                try: chunk = self._conn.recv(MAX_MESSAGE+1-len(self._in))
                except BlockingIOError: chunk = None
                if chunk == b'': raise RuntimeError('participant peer disconnected')
                if chunk:
                    if self._deadline is None: self._deadline = time.monotonic()+self._timeout
                    self._in += chunk
                    if b'\n' in self._in:
                        frame, tail = self._in.split(b'\n', 1)
                        if tail or len(frame) > MAX_MESSAGE: raise ValueError('invalid participant framing')
                        self._in = b''
                        self._command(frame)
                    elif len(self._in) > MAX_MESSAGE:
                        raise ValueError('participant command too large')
            if writable and self._out:
                try: count = self._conn.send(self._out)
                except BlockingIOError: return False
                if count <= 0: raise RuntimeError('participant receipt send failed')
                self._out = self._out[count:]
                self._within()
                if not self._out:
                    self._deadline = None
                    return True
            return False
        except BaseException:
            self._fault()
            raise
        finally:
            self._busy = False

    def close(self):
        self._owner()
        self._closed = True
        self._conn.close()
