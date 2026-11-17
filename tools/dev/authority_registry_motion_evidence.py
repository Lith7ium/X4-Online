"""Validate a local registry-fixture motion log; no gameplay/smoothness claim."""
import math
from decimal import Decimal, InvalidOperation


def _rows(text, marker):
    extracted_rows = []
    for line in text.splitlines():
        if marker not in line:
            continue
        fields = {}
        for item in line.split(marker, 1)[1].split():
            if '=' in item:
                name, value = item.split('=', 1)
                if name in fields:
                    raise ValueError('duplicate motion field')
                fields[name] = value
        extracted_rows.append(fields)
    return extracted_rows


def _float(row, key):
    value = float(row[key])
    if not math.isfinite(value):
        raise ValueError('nonfinite motion value')
    return value


def _client_sequence(row):
    raw = row['seq']
    try:
        sequence = Decimal(raw)
        if not math.isfinite(float(raw)) or not sequence.is_finite() or sequence != sequence.to_integral_value():
            raise ValueError('invalid client sequence')
    except (InvalidOperation, ValueError, OverflowError):
        raise ValueError('invalid client sequence') from None
    return int(sequence)


def validate(server, client, *, epoch, frame):
    source_rows = {}
    for row in _rows(server, 'REGISTRY_MOTION_SOURCE '):
        if row.get('epoch') != epoch or row.get('index') != '1' or row.get('frame') != frame:
            raise ValueError('source registry/frame mismatch')
        sequence = int(row['seq'])
        if sequence in source_rows:
            raise ValueError('duplicate source sequence')
        source_rows[sequence] = row
    writes = _rows(client, 'AUTHORITY_CONTINUOUS_WRITE ')
    observations = _rows(client, 'AUTHORITY_CONTINUOUS_OBSERVE ')
    readbacks_by_sequence = {}
    for row in observations:
        sequence = _client_sequence(row)
        if sequence in readbacks_by_sequence:
            raise ValueError('duplicate client readback')
        readbacks_by_sequence[sequence] = row
    if len(writes) < 5:
        raise ValueError('insufficient client writes')
    last_sequence = 0
    matched_positions = []
    for row in writes:
        sequence = _client_sequence(row)
        if sequence <= last_sequence or sequence not in source_rows:
            raise ValueError('unmatched or stale source sequence')
        last_sequence = sequence
        source_row = source_rows[sequence]
        if source_row.get('rate') != 'known':
            raise ValueError('write has unknown velocity')
        for axis in 'xyz':
            if (_float(row, axis) != _float(source_row, axis) or
                    _float(row, 'v' + axis) != _float(source_row, 'v' + axis)):
                raise ValueError('write differs from source')
            predicted = _float(row, axis) + .1 * _float(row, 'v' + axis)
            if abs(_float(row, 'target_' + axis) - predicted) > 1e-6:
                raise ValueError('invalid prediction')
        if sequence in readbacks_by_sequence:
            readback = readbacks_by_sequence[sequence]
            position_error = math.dist(
                tuple(_float(row, 'target_' + axis) for axis in 'xyz'),
                tuple(_float(readback, axis) for axis in 'xyz'),
            )
            if position_error <= 5:
                matched_positions.append(tuple(_float(readback, axis) for axis in 'xyz'))
    if (len(matched_positions) < 5 or
            max(math.dist(matched_positions[0], position) for position in matched_positions[1:]) < 10):
        raise ValueError('insufficient matching movement readbacks')
    nudges = _rows(server, 'REGISTRY_MOTION_NUDGE ')
    if len(nudges) < 3:
        raise ValueError('source nudge markers missing')
    return {'pass': True, 'source_samples': len(source_rows), 'guest_writes': len(writes),
            'matching_guest_readbacks': len(matched_positions), 'source_nudge_markers': len(nudges),
            'rate': 'source position finite difference in m/s, not native velocity',
            'scope': 'one newly created registry fixture, local UDP, paused isolated X4 instances',
            'collision_clearance_proven': False, 'atomicity_proven': False, 'npc_flight_proven': False,
            'smoothness_proven': False, 'gameplay_proven': False}
