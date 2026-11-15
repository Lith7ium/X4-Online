"""Strict evidence for the opt-in, one-write, local fixture wire experiment."""
import math
import re

NUMBER = r'[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?'
TRIPLE = rf'x=({NUMBER}) y=({NUMBER}) z=({NUMBER})'
ENROLL = re.compile(r'AUTHORITY_APPLY_ENROLL ship=([0-9a-f]{64}) sector=([0-9a-f]{64})')
REQUEST = re.compile(rf'AUTHORITY_APPLY_REQUEST request=(\d+) seq=(\d+) {TRIPLE} before_x=({NUMBER}) before_y=({NUMBER}) before_z=({NUMBER})')
LATE = re.compile(rf'AUTHORITY_APPLY_LATE elapsed=({NUMBER}) {TRIPLE}')
SOURCE = re.compile(rf'AUTHORITY_WIRE_SOURCE tick=(\d+) seq=(\d+) {TRIPLE}')
RECEIVE = re.compile(rf'AUTHORITY_WIRE_RECEIVE tick=(\d+) request=(\d+) seq=(\d+) {TRIPLE}')


def _rows(lines, tag):
    return [line.split('NATIVE_GATE ', 1)[1].strip() for line in lines
            if 'NATIVE_GATE ' in line and tag in line]


def _values(groups):
    values = tuple(float(value) for value in groups)
    if not all(math.isfinite(value) for value in values):
        raise ValueError('non-finite coordinates')
    return values


def validate(source_lines, guest_lines):
    """Cross-check role, saved identity digests, source packet, guest request and delayed observation.

    Overall gate verdict remains independent and may legitimately be divergent.
    """
    result = {'pass': False, 'errors': [], 'scope': 'one local fixture and one delayed position readback'}
    try:
        source_lines, guest_lines = list(source_lines), list(guest_lines)
        source_events = _rows(source_lines, 'AUTHORITY_APPLY_')
        guest_events = _rows(guest_lines, 'AUTHORITY_APPLY_')
        if len(source_events) != 1 or len(guest_events) != 4:
            raise ValueError('missing, extra or failed apply receipt')
        source_identity = ENROLL.fullmatch(source_events[0])
        guest_identity = ENROLL.fullmatch(guest_events[0])
        request = REQUEST.fullmatch(guest_events[1])
        late = LATE.fullmatch(guest_events[3])
        if not source_identity or not guest_identity or source_identity.groups() != guest_identity.groups():
            raise ValueError('fixture or sector identity differs')
        if not request or guest_events[2] != 'AUTHORITY_APPLY_ACK' or not late:
            raise ValueError('missing or out-of-order apply receipt')
        request_id, seq = map(int, request.groups()[:2])
        if not 1 <= request_id <= 2**53-1 or not 1 <= seq <= 2**53-1:
            raise ValueError('invalid packet sequence')
        target = _values(request.groups()[2:5]); before = _values(request.groups()[5:8])
        late_values = _values(late.groups()); elapsed, after = late_values[0], late_values[1:]
        matching_source, matching_receive = [], []
        for row in _rows(source_lines, 'AUTHORITY_WIRE_SOURCE'):
            match = SOURCE.fullmatch(row)
            if not match:
                raise ValueError('invalid source receipt')
            tick, source_seq = map(int, match.groups()[:2])
            if source_seq == seq:
                matching_source.append((tick, _values(match.groups()[2:])))
        for row in _rows(guest_lines, 'AUTHORITY_WIRE_RECEIVE'):
            match = RECEIVE.fullmatch(row)
            if not match:
                raise ValueError('invalid receive receipt')
            tick, received_request, received_seq = map(int, match.groups()[:3])
            if received_request == request_id or received_seq == seq:
                matching_receive.append((tick, received_request, received_seq, _values(match.groups()[3:])))
        if (len(matching_source) != 1 or matching_source[0][0] < 40 or matching_source[0][1] != target or
            len(matching_receive) != 1 or matching_receive[0][1:] != (request_id, seq, target)):
            raise ValueError('request does not match a unique post-stimulus source packet and guest receipt')
        displacement, error = math.dist(before, target), math.dist(after, target)
        if elapsed < 1 or displacement < 10 or error > 3:
            raise ValueError('insufficient separation, delay or delayed position accuracy')
        result.update(pass_=True, initial_separation_m=displacement, delayed_error_m=error, elapsed_s=elapsed)
        result['pass'] = result.pop('pass_')
    except (ValueError, OverflowError) as error:
        result['errors'].append(str(error))
    return result
