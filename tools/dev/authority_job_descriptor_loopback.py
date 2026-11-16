"""One-shot census job descriptor transport; no X4 or processes on import.

Caller supplies a connected, exclusively owned IPv4 loopback socket. The
functions consume it on every outcome. A fresh attempt and all source/client
process, queue, pause, witness and helper fences remain the caller's duty.
"""
import math
import re

import authority_descriptor_loopback as stream

_NAME=re.compile(r'[A-Za-z0-9_.-]{1,128}\Z',re.ASCII)
_FIELDS=frozenset(('version','type','attempt','epoch','transport_sequence','job_sequence',
                   'index','macro','faction','sector_macro','x','y','z'))
_ACK_FIELDS=frozenset(('version','type','attempt','epoch','transport_sequence','job_sequence','index'))
_MAX_EXACT_INTEGER=9007199254740991
_COORD_LIMIT=10000000


def _sequence(value):
    return type(value) is int and 1<=value<=_MAX_EXACT_INTEGER


def _descriptor(value):
    if type(value) is not dict or set(value)!=_FIELDS:raise ValueError('invalid job descriptor fields')
    if (type(value['version']) is not int or value['version']!=1 or value['type']!='job_descriptor'
            or not stream._token(value['attempt']) or not stream._token(value['epoch'])
            or type(value['transport_sequence']) is not int or value['transport_sequence']!=1
            or not _sequence(value['job_sequence']) or type(value['index']) is not int or value['index']!=10055):
        raise ValueError('invalid job descriptor identity')
    for name in ('macro','faction','sector_macro'):
        v=value[name]
        if type(v) is not str or not _NAME.fullmatch(v) or v.lower() in ('nil','null'):
            raise ValueError('invalid job descriptor name')
    for name in ('x','y','z'):
        n=value[name]
        if type(n) not in (int,float) or abs(n)>_COORD_LIMIT or not math.isfinite(n):
            raise ValueError('invalid sector coordinate')
    return dict(value)


def _ack(desc):
    return {name:('witness_ack' if name=='type' else desc[name]) for name in _ACK_FIELDS}


def send_descriptor(sock,descriptor,deadline,guard):
    """Send one descriptor and accept only its exactly correlated witness ACK."""
    try:
        stream._socket(sock)
        desc=_descriptor(descriptor)
        sock.setblocking(False)
        stream._check(deadline,guard)
        stream._write(sock,stream._encode(desc),deadline,guard)
        response=stream._read(sock,deadline,guard)
        if (type(response) is not dict or set(response)!=_ACK_FIELDS or response!=_ack(desc)
                or any(type(response[k]) is not int for k in ('version','transport_sequence','job_sequence','index'))):
            raise ValueError('invalid witness ACK')
        stream._check(deadline,guard)
        return True
    finally:
        sock.close()


def receive_descriptor(sock,expected_attempt,expected_epoch,expected_job_sequence,witness_check,deadline,guard):
    """ACK only after the correlated local witness callback and a further guard."""
    try:
        stream._socket(sock)
        if (not stream._token(expected_attempt) or not stream._token(expected_epoch)
                or not _sequence(expected_job_sequence) or not callable(witness_check)):
            raise ValueError('invalid witness context')
        sock.setblocking(False)
        stream._check(deadline,guard)
        desc=_descriptor(stream._read(sock,deadline,guard))
        if (desc['attempt']!=expected_attempt or desc['epoch']!=expected_epoch
                or desc['job_sequence']!=expected_job_sequence):
            raise ValueError('foreign attempt, epoch or job sequence')
        stream._quiet(sock,deadline,guard)
        accepted=witness_check(dict(desc))
        stream._check(deadline,guard)
        if accepted is not True:raise RuntimeError('local witness not confirmed')
        stream._quiet(sock,deadline,guard)
        stream._write(sock,stream._encode(_ack(desc)),deadline,guard)
        stream._check(deadline,guard)
        return desc
    finally:
        sock.close()
