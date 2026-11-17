"""One private, explicitly requested throttle impulse; no game is launched."""
import math
import os
import re
import select
import socket
import threading
import time

from authority.experimental_participant_job_ipc import _LOCK, _OWNERS
from authority_tcp_job_client_live import socket_owner
from authority_tcp_native_worker import check_process

TIMING_NAMES = ('external_guard', 'socket_owner', 'pump')
TOKEN = re.compile(r'[0-9a-f]{32}\Z')
NUMBER = re.compile(r'[+]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?\Z')


class ThrottleUnconfirmed(RuntimeError):
    """An attempt may have reached X4; stop the owned disposable process."""
    def __init__(self, message=None, *, attempted, started, stopped, phase='unknown', error_class='other_error',
                 started_phase_datagram_received=False, stopped_phase_datagram_received=False, elapsed_ms=0, work_timing=None):
        # The optional message is ignored for compatibility with older callers.
        super().__init__('fixture throttle unconfirmed')
        self.attempted, self.started, self.stopped = attempted, started, stopped
        # Fixed, nonsecret metadata; no raw packet or exception text is exported.
        self.phase, self.error_class = phase, error_class
        self.started_phase_datagram_received = started_phase_datagram_received
        self.stopped_phase_datagram_received = stopped_phase_datagram_received
        self.elapsed_ms = elapsed_ms
        self.work_timing = ({name: {'calls': 0, 'elapsed_ms': 0} for name in TIMING_NAMES}
                            if work_timing is None else work_timing)


def pulse(sock, *, process, lease, attempt, epoch, generation, nonce, slot,
          guard, running, pump, timeout=15):
    """Dispatch once after the caller established a participant baseline.

    `STOPPED` confirms an MD action receipt only. On any failure after send
    begins, the caller must stop the disposable X4 and must not retry.
    """
    tokens = (lease, attempt, epoch, generation, nonce)
    if (type(sock) is not socket.socket or sock.family != socket.AF_INET or
            sock.getsockopt(socket.SOL_SOCKET, socket.SO_TYPE) != socket.SOCK_DGRAM or
            type(process) is not dict or type(slot) is not int or slot not in (1, 2) or
            any(type(value) is not str or not TOKEN.fullmatch(value) for value in tokens) or
            len(set(tokens)) != len(tokens) or not all(callable(fn) for fn in (guard, running, pump)) or
            type(timeout) not in (int, float) or not math.isfinite(timeout) or not 3 <= timeout <= 30):
        raise ValueError('invalid private throttle context')
    local = sock.getsockname()
    if local[0] != '127.0.0.1' or not local[1]: raise ValueError('private throttle socket required')
    identity = dict(process)
    thread = threading.get_ident()
    fd = sock.fileno()
    descriptor = os.fstat(fd)
    fd_identity = (descriptor.st_dev, descriptor.st_ino)
    began = time.monotonic()
    deadline = began + timeout
    suffix = '|'.join((*tokens, str(slot))).encode('ascii')
    attempted = started = stopped = False
    started_phase_datagram_received = stopped_phase_datagram_received = False
    phase = 'waiting_ready'
    peer = None
    work_timing = {name: {'calls': 0, 'elapsed_ms': 0} for name in TIMING_NAMES}
    work_seconds = {name: 0.0 for name in TIMING_NAMES}
    def observe_clock():
        # Diagnostics must never replace a protocol/guard exception.
        try:
            value = time.monotonic()
            return value if math.isfinite(value) else None
        except BaseException:
            return None
    def measured(name, callback, *args):
        # Direct callback time only; pump time includes its own nested guards.
        work_timing[name]['calls'] += 1
        before = observe_clock()
        try:
            return callback(*args)
        finally:
            try:
                after = observe_clock()
                if before is not None and after is not None and after >= before:
                    elapsed_seconds = work_seconds[name] + (after - before)
                    elapsed_ms = int(elapsed_seconds * 1000)
                    work_seconds[name] = elapsed_seconds
                    work_timing[name]['elapsed_ms'] = elapsed_ms
            except BaseException:
                pass
    def check():
        if time.monotonic() >= deadline: raise TimeoutError('throttle deadline')
        if threading.get_ident() != thread or sock.fileno() != fd:
            raise RuntimeError('throttle socket or owner thread changed')
        current = os.fstat(fd)
        if (current.st_dev, current.st_ino) != fd_identity:
            raise RuntimeError('throttle socket descriptor changed')
        check_process(dict(identity))
        if measured('external_guard', guard) is not True or running() is not True or sock.getsockname() != local:
            raise RuntimeError('throttle context changed')
        if peer is not None and measured('socket_owner', socket_owner, peer, local, dict(identity)) is not True:
            raise RuntimeError('throttle peer ownership changed')
        check_process(dict(identity))
        current = os.fstat(fd)
        if sock.fileno() != fd or (current.st_dev, current.st_ino) != fd_identity:
            raise RuntimeError('throttle socket descriptor changed after peer check')
        if measured('external_guard', guard) is not True or running() is not True or sock.getsockname() != local:
            raise RuntimeError('throttle context changed after peer check')
        current = os.fstat(fd)
        if (threading.get_ident() != thread or sock.fileno() != fd or
                (current.st_dev, current.st_ino) != fd_identity):
            raise RuntimeError('throttle socket or owner changed during guard')
        if peer is not None and measured('socket_owner', socket_owner, peer, local, dict(identity)) is not True:
            raise RuntimeError('throttle peer changed during guard')
        if time.monotonic() >= deadline: raise TimeoutError('throttle deadline')
    def receive(expected, *, next_receipt_allowed=False):
        nonlocal peer, phase, started_phase_datagram_received, stopped_phase_datagram_received
        while True:
            check()
            readable, _, exceptional = select.select([sock], [], [sock], min(.05, max(0, deadline-time.monotonic())))
            check()
            if exceptional: raise RuntimeError('throttle socket failed')
            if readable:
                data, source = sock.recvfrom(769)
                if expected == b'STARTED':
                    started_phase_datagram_received = True
                    phase = 'validating_started'
                elif expected == b'STOPPED':
                    stopped_phase_datagram_received = True
                    phase = 'validating_stopped'
                else:
                    phase = 'validating_ready'
                stop_time = None
                prefix = expected + b'|' + suffix
                if expected == b'STOPPED' and data.startswith(prefix + b'|'):
                    try: text = data[len(prefix)+1:].decode('ascii')
                    except UnicodeError: raise ValueError('invalid throttle stop time') from None
                    if len(text) > 32 or not NUMBER.fullmatch(text): raise ValueError('invalid throttle stop time')
                    stop_time = float(text)
                    if not math.isfinite(stop_time) or not 0 <= stop_time <= 1e12:
                        raise ValueError('invalid throttle stop time')
                elif data != prefix:
                    raise ValueError('throttle receipt differs')
                if expected == b'STOPPED' and stop_time is None:
                    raise ValueError('throttle stop time missing')
                if source[0] != '127.0.0.1' or not source[1]:
                    raise ValueError('throttle receipt differs')
                if peer is None: peer = source
                elif source != peer: raise ValueError('throttle peer changed')
                check()
                if not next_receipt_allowed and select.select([sock], [], [sock], 0)[0]:
                    raise ValueError('unexpected throttle packet')
                check()
                return stop_time
            measured('pump', pump)
            check()
    with _LOCK:
        if sock in _OWNERS: raise ValueError('throttle socket already owned')
        sock.setblocking(False)
        _OWNERS[sock] = True
    try:
        receive(b'READY')
        phase = 'sending_go'
        packet = b'GO|' + suffix
        check()
        attempted = True
        if sock.sendto(packet, peer) != len(packet): raise RuntimeError('throttle dispatch incomplete')
        check()
        phase = 'waiting_started'
        receive(b'STARTED', next_receipt_allowed=True); started = True
        phase = 'waiting_stopped'
        stop_game_time = receive(b'STOPPED'); stopped = True
        phase = 'final_check'
        check()
        return {'start_dispatched': True, 'start_acknowledged': True, 'stop_acknowledged': True,
                'stop_game_time': stop_game_time, 'movement_proven': False, 'human_input_proven': False, 'stationary_proven': False}
    except BaseException as error:
        # Only fixed categories are exported: exception messages can contain
        # peer data or other sensitive context.
        if isinstance(error, TimeoutError): error_class = 'timeout'
        elif isinstance(error, ValueError): error_class = 'invalid_value'
        elif isinstance(error, RuntimeError): error_class = 'runtime_error'
        elif isinstance(error, OSError): error_class = 'os_error'
        elif isinstance(error, Exception): error_class = 'other_error'
        else: error_class = 'interrupted'
        elapsed_ms = 0
        try:
            ended = observe_clock()
            if ended is not None:
                elapsed_ms = max(0, int((ended - began) * 1000))
        except BaseException:
            pass
        raise ThrottleUnconfirmed(
            attempted=attempted, started=started, stopped=stopped, phase=phase,
            error_class=error_class, started_phase_datagram_received=started_phase_datagram_received,
            stopped_phase_datagram_received=stopped_phase_datagram_received, elapsed_ms=elapsed_ms,
            work_timing=work_timing) from None
    finally:
        with _LOCK:
            _OWNERS.pop(sock, None)
