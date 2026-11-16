"""One-shot, experimental loopback descriptor test transport; no X4 on import.

Both entry points consume and close their connected socket on every outcome.
The caller exclusively owns each socket and must fence processes independently.
The synchronous guard and inspect callbacks are checked before/after return;
they are not preempted by this module's deadline. Never retry an ambiguous send.
"""
import json
import math
import re
import select
import socket
import time

_LIMIT = 1024
_WAIT_POLL_SECONDS = 0.2
_TOKEN = re.compile(r'[0-9a-f]{32}\Z', re.ASCII)
_NAME = re.compile(r'[A-Za-z0-9_.-]{1,128}\Z', re.ASCII)
_FIELDS = frozenset(('version', 'type', 'attempt', 'epoch', 'seq', 'index',
                     'macro', 'sector', 'owner', 'seed', 'x', 'y', 'z'))
_ACK_FIELDS = frozenset(('version', 'type', 'attempt', 'epoch', 'seq', 'index'))


def _token(value):
    return type(value) is str and _TOKEN.fullmatch(value) is not None


def _descriptor(value):
    if type(value) is not dict or set(value) != _FIELDS:
        raise ValueError('invalid descriptor fields')
    if (type(value['version']) is not int or value['version'] != 1 or value['type'] != 'descriptor'
            or not _token(value['attempt']) or not _token(value['epoch'])
            or type(value['seq']) is not int or value['seq'] != 1
            or type(value['index']) is not int or value['index'] != 3):
        raise ValueError('invalid descriptor identity')
    for name in ('macro', 'sector', 'owner'):
        if type(value[name]) is not str or not _NAME.fullmatch(value[name]) or value[name].lower() in ('nil', 'null'):
            raise ValueError('invalid descriptor name')
    if type(value['seed']) is not int or not 0 <= value['seed'] <= 2147483647:
        raise ValueError('invalid seed')
    for name in ('x', 'y', 'z'):
        n = value[name]
        if type(n) not in (int, float) or not math.isfinite(n) or abs(n) > 10000000:
            raise ValueError('invalid coordinate')
    return dict(value)


def _ack(desc):
    return {name: ('ack' if name == 'type' else desc[name]) for name in _ACK_FIELDS}


def _decode(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('duplicate JSON key')
            result[key] = value
        return result
    def bad_constant(_):
        raise ValueError('invalid JSON constant')
    try:
        return json.loads(raw.decode('utf-8'), object_pairs_hook=unique, parse_constant=bad_constant)
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise ValueError('invalid frame') from exc


def _encode(value):
    raw = json.dumps(value, ensure_ascii=True, allow_nan=False, separators=(',', ':')).encode('ascii')
    if not raw or len(raw) > _LIMIT:
        raise ValueError('frame too large')
    return raw + b'\n'


def _check(deadline, guard):
    if type(deadline) not in (int, float) or not math.isfinite(deadline) or time.monotonic() >= deadline:
        raise TimeoutError('deadline expired')
    if not callable(guard) or guard() is not True:
        raise RuntimeError('guard failed')
    if time.monotonic() >= deadline:
        raise TimeoutError('deadline expired')


def _socket(sock):
    if not isinstance(sock, socket.socket) or sock.family != socket.AF_INET or sock.type != socket.SOCK_STREAM:
        raise ValueError('IPv4 stream socket required')
    if sock.getsockname()[0] != '127.0.0.1' or sock.getpeername()[0] != '127.0.0.1':
        raise ValueError('loopback connection required')


def _wait(sock, write, deadline, guard):
    while True:
        _check(deadline, guard)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError('deadline expired')
        readable, writable, exceptional = select.select(
            [] if write else [sock], [sock] if write else [], [sock],
            min(_WAIT_POLL_SECONDS, remaining))
        _check(deadline, guard)
        if exceptional:
            raise TimeoutError('socket wait failed')
        if writable if write else readable:
            return


def _write(sock, data, deadline, guard):
    offset = 0
    while offset < len(data):
        _wait(sock, True, deadline, guard)
        try:
            n = sock.send(data[offset:])
        except BlockingIOError:
            continue
        if n <= 0:
            raise ConnectionError('socket closed during write')
        offset += n
        _check(deadline, guard)


def _read(sock, deadline, guard):
    raw = bytearray()
    while True:
        _wait(sock, False, deadline, guard)
        try:
            chunk = sock.recv(_LIMIT + 1 - len(raw))
        except BlockingIOError:
            continue
        if not chunk:
            raise ConnectionError('socket closed before frame')
        if b'\n' in chunk:
            body, tail = chunk.split(b'\n', 1)
            if tail:
                raise ValueError('unexpected trailing frame data')
            raw.extend(body)
            return _decode(raw)
        raw.extend(chunk)
        if len(raw) > _LIMIT:
            raise ValueError('frame too large')


def _quiet(sock, deadline, guard):
    _check(deadline, guard)
    readable, _, exceptional = select.select([sock], [], [sock], 0)
    _check(deadline, guard)
    if exceptional or readable:
        raise ConnectionError('peer closed or sent unexpected data')


def send_descriptor(sock, descriptor, deadline, guard):
    """Send one descriptor and require its matching inspect ACK; consumes socket."""
    try:
        _socket(sock)
        desc = _descriptor(descriptor)
        sock.setblocking(False)
        _check(deadline, guard)
        _write(sock, _encode(desc), deadline, guard)
        response = _read(sock, deadline, guard)
        if type(response) is not dict or set(response) != _ACK_FIELDS or response != _ack(desc):
            raise ValueError('invalid ACK')
        # bool must never compare equal to integer protocol fields.
        if any(type(response[k]) is not int for k in ('version', 'seq', 'index')):
            raise ValueError('invalid ACK integer')
        _check(deadline, guard)
        return True
    finally:
        sock.close()


def receive_descriptor(sock, expected_attempt, expected_epoch, inspect, deadline, guard):
    """Inspect one matching descriptor and ACK only after exact True; consumes socket."""
    try:
        _socket(sock)
        if not _token(expected_attempt) or not _token(expected_epoch) or not callable(inspect):
            raise ValueError('invalid receiver context')
        sock.setblocking(False)
        _check(deadline, guard)
        desc = _descriptor(_read(sock, deadline, guard))
        if desc['attempt'] != expected_attempt or desc['epoch'] != expected_epoch:
            raise ValueError('foreign attempt or epoch')
        _quiet(sock, deadline, guard)
        outcome = inspect(dict(desc))
        _check(deadline, guard)
        if outcome is not True:
            raise RuntimeError('local inspect not confirmed')
        _quiet(sock, deadline, guard)
        _write(sock, _encode(_ack(desc)), deadline, guard)
        _check(deadline, guard)
        return desc
    finally:
        sock.close()
