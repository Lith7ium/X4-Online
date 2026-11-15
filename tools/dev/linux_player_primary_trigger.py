"""Finite scripted primary experiment; Linux input still rejects shared FIRE."""
import hashlib
from pathlib import Path
import re

SOURCES = tuple('src/native/engine/linux/' + name for name in (
    'player_primary_trigger.h', 'player_primary_trigger.md', 'gate_player_primary_trigger.h',
    'test_gate_player_primary_trigger.c', 'test_player_physics_network.c',
    'test_stock_keyboard_replay_adapter.c', 'gate_player_physics_network.h',
    'gate_stock_keyboard_replay.h', 'gate_player_fire_observation.h',
    'player_weapon_groups.h', 'gate_linux.c',
)) + ('tools/dev/linux_player_primary_trigger.py', 'tests/test_linux_player_primary_trigger.py')
HELPERS = ('linux_player_primary_trigger.py',)
PREFIX = 'X4LAN PRIMARY_TRIGGER '
HUMAN_PREFIX = 'X4LAN PRIMARY_HUMAN '


def human_enabled(options):
    active = options.get('player_primary_human', False)
    if type(active) is not bool:
        raise ValueError('human primary must be boolean')
    return active


def enabled(options):
    scripted = options.get('player_primary_trigger_experiment', False)
    human = human_enabled(options)
    if type(scripted) is not bool or (scripted and human):
        raise ValueError('primary script and human modes are mutually exclusive booleans')
    active = scripted or human
    if active and (options.get('worker_dispatch') is not True or
                   options.get('player_startup_phases') != 'v1-t40' or
                   type(options.get('player_ui_session_frames')) is not int or
                   not 180 <= options['player_ui_session_frames'] <= 900 or
                   options.get('independent_keyboard_frames') != options['player_ui_session_frames']):
        raise ValueError('primary trigger experiment requires worker dispatch and finite T40 physics')
    if human and (options.get('player_primary_capture') is not True or
                  options.get('player_cursor_active_flight') is not True):
        raise ValueError('human primary requires admitted capture and active flight cursor')
    return active


def validate_local_mode(options, external):
    if type(external) is not bool:
        raise ValueError('external relay mode must be boolean')
    if human_enabled(options) and external:
        raise ValueError('human primary requires both local clients from the same sealed bundle; remote capability is not negotiated')


def environment(env, active, human=False):
    if type(active) is not bool or type(human) is not bool or (human and not active):
        raise ValueError('invalid primary mode')
    result = dict(env)
    result.pop('X4_DEV_PRIMARY_TRIGGER', None)
    if active:
        result['X4_DEV_PRIMARY_TRIGGER'] = 'human-v1' if human else 'script-v1'
    return result


def collect(stderr, physics, options):
    errors = []
    rows = []
    try:
        active = enabled(options)
        raw = Path(stderr).read_bytes()
        human = human_enabled(options)
        prefix = HUMAN_PREFIX if human else PREFIX
        all_rows = [line for line in raw.decode('utf-8').splitlines() if PREFIX.strip() in line or HUMAN_PREFIX.strip() in line]
        rows = [line for line in all_rows if prefix.strip() in line]
        if len(rows) != len(all_rows):
            raise ValueError('primary receipt mode mismatch')
        if not active:
            if rows:
                raise ValueError('unexpected primary trigger receipt')
        else:
            if (physics.get('pass') is not True or
                    physics.get('stderr_sha256') != hashlib.sha256(raw).hexdigest()):
                raise ValueError('primary trigger lacks hash-bound accepted physics')
            frames = physics.get('frames', [])
            if [frame['tick'] for frame in frames] != list(range(40, 40 + options['player_ui_session_frames'])):
                raise ValueError('primary trigger physics window incomplete')
            if len(rows) != len(frames):
                raise ValueError('primary trigger receipt range incomplete')
            if human:
                return collect_human(rows, physics, options, frames)
            pattern = re.compile(PREFIX + r'v=1 tick=([0-9]+) worker=([0-9]+) script=([01]) p1=([0-9]+) p2=([0-9]+) firing1=([0-9]+) firing2=([0-9]+) terminate_only=1')
            counts = None
            for row, frame in zip(rows, frames):
                match = pattern.fullmatch(row)
                if not match:
                    raise ValueError('malformed primary trigger receipt')
                tick, worker, trigger, p1, p2, firing1, firing2 = map(int, match.groups())
                if (tick != frame['tick'] or worker != frame['worker_thread'] or
                        trigger != int(70 <= tick < 76) or not 1 <= p1 <= 16 or not 1 <= p2 <= 16 or
                        not 0 <= firing1 <= p1 or not 0 <= firing2 <= p2 or
                        (counts is not None and counts != (p1, p2))):
                    raise ValueError('primary trigger sequence, worker, burst or group drift')
                counts = p1, p2
    except (OSError, UnicodeError, ValueError, KeyError, TypeError) as error:
        errors.append(str(error))
    return {'pass': not errors, 'errors': errors, 'raw_receipts': rows,
            'receipt_count': len(rows), 'human_trigger_replay': False,
            'combat_determinism_proven': False}


def collect_human(rows, physics, options, frames):
    """Bind desired states to both accepted delayed wire records, never focus."""
    errors = []
    try:
        pattern = re.compile(HUMAN_PREFIX + r'v=1 tick=([0-9]+) worker=([0-9]+) want1=([01]) want2=([01]) p1=([0-9]+) p2=([0-9]+) firing1=([0-9]+) firing2=([0-9]+) terminate_only=1')
        records = physics['slot_records']
        if any(len(records[str(slot)]) != len(frames) for slot in (1, 2)):
            raise ValueError('human primary lacks complete accepted wire streams')
        counts = None
        for index, (row, frame) in enumerate(zip(rows, frames)):
            match = pattern.fullmatch(row)
            if not match:
                raise ValueError('malformed human primary receipt')
            tick, worker, one, two, p1, p2, firing1, firing2 = map(int, match.groups())
            wants = []
            for slot in (1, 2):
                data = bytes.fromhex(records[str(slot)][index])
                if len(data) < 43 or data[0] != 3 or data[1] & 32:
                    raise ValueError('unsupported human primary wire')
                wants.append(int(bool(data[1] & 16)))
            if (tick != frame['tick'] or worker != frame['worker_thread'] or
                    [one, two] != wants or not 1 <= p1 <= 16 or not 1 <= p2 <= 16 or
                    not 0 <= firing1 <= p1 or not 0 <= firing2 <= p2 or
                    (counts is not None and counts != (p1, p2))):
                raise ValueError('human primary wire, generation, worker or group mismatch')
            counts = p1, p2
        if rows and (one or two):
            raise ValueError('human primary final delayed drain is not neutral')
    except (ValueError, KeyError, TypeError, IndexError) as error:
        errors.append(str(error))
    return {'pass': not errors, 'errors': errors, 'raw_receipts': rows,
            'receipt_count': len(rows), 'human_trigger_replay': not errors,
            'combat_determinism_proven': False, 'native_input_causation_proven': False}
