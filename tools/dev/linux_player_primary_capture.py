"""Capture-only primary ledger. No shared FIRE admission or native forwarding."""
import hashlib
from pathlib import Path
import re
import math
import struct

import linux_player_primary_trigger as trigger

SOURCES = tuple('src/native/engine/linux/' + name for name in (
    'player_primary_capture.h', 'gate_player_primary_capture.h',
    'test_gate_player_primary_capture.c', 'player_primary_capture.md',
)) + ('tools/dev/linux_player_primary_capture.py', 'tests/test_linux_player_primary_capture.py')
HELPERS = ('linux_player_primary_capture.py',)
PREFIX = 'X4LAN PRIMARY_CAPTURE '


def enabled(options):
    active = options.get('player_primary_capture', False)
    if type(active) is not bool:
        raise ValueError('primary capture must be boolean')
    if active:
        trigger.enabled(dict(options, player_primary_trigger_experiment=True, player_primary_human=False))
        if options.get("player_cursor_active_flight") is not True:
            raise ValueError("primary capture requires active-flight cursor focus")
        if options.get('player_primary_trigger_experiment'):
            raise ValueError('primary capture and scripted firing are mutually exclusive')
    return active


def environment(env, active):
    if type(active) is not bool:
        raise ValueError('primary capture activation must be boolean')
    result = dict(env)
    result.pop('X4_DEV_PRIMARY_CAPTURE', None)
    if active:
        result['X4_DEV_PRIMARY_CAPTURE'] = 'capture-v1'
    return result


def collect(stderr, physics, options, slot):
    rows, errors, held_count, edge_count, active_count = [], [], 0, 0, 0
    try:
        raw = Path(stderr).read_bytes()
        rows = [line for line in raw.decode('utf-8').splitlines() if PREFIX.strip() in line]
        if not enabled(options):
            if rows:
                raise ValueError('unexpected primary capture receipt')
        else:
            if (physics.get('pass') is not True or
                    physics.get('stderr_sha256') != hashlib.sha256(raw).hexdigest()):
                raise ValueError('primary capture lacks hash-bound accepted physics')
            frames = options['player_ui_session_frames']
            if [frame['tick'] for frame in physics['frames']] != list(range(40, 40 + frames)):
                raise ValueError('primary capture physics window incomplete')
            edge = re.compile(PREFIX + r'v=1 stage=edge tick=(\d+) index=(\d+) family=([01]) kind=([12]) id=(\d+) raw=([0-9a-f]{8}) held=([01]) primary=([01]) focused=([01]) context=([01]) native_forward=0')
            held = re.compile(PREFIX + r'v=1 stage=held tick=(\d+) slot=([12]) focused=([01]) context=([01]) held=([01]) edges=(\d+) banks_neutral=1 wire_fire=0 native_forward=0')
            tick, pending = 38, 0
            for row in rows:
                match = edge.fullmatch(row)
                if match:
                    generation, index, family, kind, identity, bits, pressed, primary, focus, context = match.groups()
                    kind, identity = int(kind), int(identity)
                    valid_ids = (0x18, 0x19, 0x30, 0x31) if kind == 1 else (0x11, 0x12, 0x13, 0x14)
                    if (int(generation) != tick or int(index) != pending or pending >= 128 or
                            identity not in valid_ids or int(primary) != int(identity in (0x18, 0x30, 0x11, 0x13))):
                        raise ValueError('primary capture edge order or identity')
                    raw_bits = int(bits, 16)
                    value = struct.unpack("<f", struct.pack("<I", raw_bits))[0]
                    threshold = struct.unpack("<f", struct.pack("<I", 0x38d1b717))[0]
                    if ((kind == 1 and (raw_bits > 1 or int(pressed) != raw_bits)) or
                            (kind == 2 and (not math.isfinite(value) or int(pressed) != int(abs(value) >= threshold)))):
                        raise ValueError("primary capture raw native predicate")
                    pending += 1
                    edge_count += 1
                    continue
                match = held.fullmatch(row)
                if not match:
                    raise ValueError('malformed primary capture receipt')
                generation, own_slot, focus, context, pressed, count = map(int, match.groups())
                if (generation != tick or own_slot != slot or count != pending or
                        (pressed and (not focus or not context)) or tick >= 38 + frames):
                    raise ValueError('primary capture held order, focus or slot')
                active_count += pressed
                held_count += 1
                tick += 1
                pending = 0
            if pending or tick != 38 + frames:
                raise ValueError('primary capture range incomplete')
    except (OSError, UnicodeError, ValueError, KeyError, TypeError) as error:
        errors.append(str(error))
    return dict(errors=errors, raw_receipts=rows,
                held_count=held_count, edge_count=edge_count, active_count=active_count,
                human_trigger_replay=False, combat_determinism_proven=False) | {'pass': not errors}
