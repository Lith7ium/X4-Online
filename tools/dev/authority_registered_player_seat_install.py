"""Install one opt-in registered player seat into a private join overlay.

The caller owns checkpoint provenance, the processes, the private profile and
the final log check. This module starts no processes and proves no gameplay.
"""
import math
from pathlib import Path
import re
import shutil

import authority_fixture_checkpoint_source as fixture_source
import authority_saved_player_control_live as seat
import authority_saved_fixture_log as fixture_log
import authority_download_load_live as load

ROOT = Path(__file__).resolve().parents[2]
TAG = b'[X4LAN] AUTH_REGISTERED_PLAYER_SEAT '
ACTION_TAG = b'[X4LAN] AUTH_PLAYER_CONTROL_MD '


def install(case, profile, *, slot, nonce, epoch, timeout, scripts):
    """Add a bounded seat gate to an already installed private client loader."""
    if (type(slot) is not int or slot not in (1, 2) or
            not isinstance(nonce, str) or not re.fullmatch(r'[0-9a-f]{32}', nonce) or
            not isinstance(epoch, str) or not re.fullmatch(r'[0-9a-f]{32}', epoch) or
            type(timeout) not in (int, float) or not math.isfinite(timeout) or not 0 < timeout <= 120):
        raise ValueError('invalid registered player seat context')
    if type(scripts) is not dict or set(scripts) != set(fixture_source.SAVED_SCRIPTS):
        raise ValueError('confirmed saved script set required')
    for name, data in scripts.items():
        expected = (fixture_source.fixture_save.historical_registry() if name == 'authority_ship_registry.xml'
                    else ROOT / 'tools/dev' / name)
        if type(data) is not bytes or data != expected.read_bytes():
            raise ValueError('saved fixture script differs: ' + name)
    case = Path(case).resolve(strict=True)
    profile = Path(profile).resolve(strict=True)
    if not profile.is_relative_to(case) or profile.name != '45841':
        raise ValueError('private client profile required')
    lab = case / 'extensions/x4_lan_lab'; ui = lab / 'ui'; md = lab / 'md'
    manifest = lab / 'ui.xml'; config = ui / 'config.lua'
    marker = ui / 'authority_checkpoint_marker_probe.lua'
    loader = ui / 'authority_download_load_probe.lua'
    manifest_text = manifest.read_text(encoding='utf-8')
    config_text = config.read_text(encoding='ascii')
    marker_text = marker.read_text(encoding='utf-8')
    loader_text = loader.read_text(encoding='utf-8')
    if not config_text.endswith('}\n'):
        raise ValueError('unexpected client configuration')
    if 'X4AuthorityCheckpointMarker' not in marker_text:
        raise ValueError('client fixture marker hook unavailable')
    marker_text = marker_text.replace('X4AuthorityCheckpointMarker', 'X4AuthorityPlayerFixtureMarker')
    hook = '  if not X4LAN_AUTHORITY_MARKER_READY() then return end\n'
    gate = '''  if not engine.is_paused() then
   if registered_seat_pause_confirmed then error('registered seat pause lost') end
   if not registered_seat_pause_requested then registered_seat_pause_requested=true;engine.pause() end
   return
  end
  registered_seat_pause_confirmed=true
  if not X4LAN_REGISTERED_PLAYER_CONTROL_TICK() then return end
'''
    loader_text = seat.replace_once(loader_text, "local state='initial';local failed=false\n",
        "local state='initial';local failed=false\nlocal registered_seat_pause_requested=false;local registered_seat_pause_confirmed=false\n")
    loader_text = seat.replace_once(loader_text, hook, hook + gate)
    modules = ('authority_registry_resolve_string.lua', 'authority_player_control_once.lua',
               'authority_player_control_live_owner.lua', 'authority_registered_player_control_owner.lua')
    manifest_hook = '    <file name="ui/authority_download_load_probe.lua" />\n'
    additions = ''.join('    <file name="ui/' + name + '" />\n' for name in modules)
    manifest_text = seat.replace_once(manifest_text, manifest_hook, additions + manifest_hook)
    config_text = config_text[:-2] + (',authority_registered_player_control=true,'
        f'authority_fixture_epoch="{epoch}",authority_fixture_nonce="{nonce}",'
        f'authority_fixture_slot={slot},authority_fixture_timeout={timeout:.17g}' + '}\n')
    for name, data in scripts.items():
        (md / name).write_bytes(data)
    cue = md / 'authority_registered_player_control.xml'
    shutil.copyfile(ROOT / 'tools/dev/authority_registered_player_control.xml', cue)
    installed = []
    for name in modules:
        target = ui / name
        shutil.copyfile(ROOT / 'tools/dev' / name, target)
        installed.append(target)
    once = ui / 'authority_player_control_once.lua'
    once.write_text(seat.replace_once(once.read_text(encoding='utf-8'),
        'local args={epoch=o.epoch,request_id=o.nonce}',
        'local args={epoch=o.epoch,request_id=o.nonce,slot=o.slot}'), encoding='utf-8')
    marker.write_text(marker_text, encoding='utf-8')
    loader.write_text(loader_text, encoding='utf-8')
    manifest.write_text(manifest_text, encoding='utf-8')
    config.write_text(config_text, encoding='ascii')
    return [*(md / name for name in scripts), cue, *installed, marker, loader, manifest, config]


def verify_log(path, *, nonce, slot, ticket, marker):
    """Require correlated seat, action and load receipts from one private log."""
    if (type(slot) is not int or slot not in (1, 2) or
            not isinstance(nonce, str) or not re.fullmatch(r'[0-9a-f]{32}', nonce) or
            not isinstance(marker, str) or not re.fullmatch(r'[0-9a-f]{32}', marker)):
        raise ValueError('invalid seat log context')
    captured = fixture_log.capture(path, None, 32 << 20)
    if captured is None:
        raise ValueError('seat log unavailable')
    raw = captured[0]
    if not raw.endswith(b'\n'):
        raw = raw.rsplit(b'\n', 1)[0] + b'\n' if b'\n' in raw else b''
    lower = raw.lower()
    if any(fault in lower for fault in (b'error while parsing expression:', b'maximum operator nesting level reached',
            b'could not find suitable data type for conversion!', b'invalid data types for arithmetic operation!',
            b'error in md cue md.x4authority', b'error in lua script', b'stack traceback:',
            b'[x4lan] auth_download_load error')):
        raise ValueError('registered player seat engine fault')
    lines = raw.splitlines()
    rows = [(i, line.split(TAG, 1)[1].strip()) for i, line in enumerate(lines) if TAG in line]
    prefix = nonce.encode('ascii') + b' '
    if not rows or any(not value.startswith(prefix) for _, value in rows):
        raise ValueError('foreign or missing seat receipt')
    values = tuple(value[len(prefix):].decode('ascii') for _, value in rows)
    fenced = f'FENCED slot={slot} index={slot + 2}'
    existing = ('START', 'CREATED', 'EXISTING', 'FIRST', 'CONTROLLED', 'DONE', fenced)
    takeover = ('START', 'CREATED', 'BEFORE', 'INTENT_TELEPORT', 'LOCAL_CALL_RETURNED',
                'DISPATCH', 'FIRST', 'CONTROLLED', 'DONE', fenced)
    if values not in (existing, takeover):
        raise ValueError('seat receipts incomplete or ambiguous')
    actions = [(i, line.split(ACTION_TAG, 1)[1].strip()) for i, line in enumerate(lines) if ACTION_TAG in line]
    if values == existing:
        if actions:
            raise ValueError('existing seat unexpectedly teleported')
    else:
        if tuple(value for _, value in actions) != (b'ACTION_BEGIN', b'ACTION_RETURNED'):
            raise ValueError('seat teleport receipt missing')
        if not (rows[3][0] < actions[0][0] < actions[1][0] < rows[5][0]):
            raise ValueError('seat teleport receipts out of order')
    watch = load.ReceiptWatch(path, ticket)
    needles = (load.TAG + watch.expected[0], b'AUTH_MARKER load INSPECTED ' + marker.encode('ascii'),
               TAG + prefix + b'START', TAG + prefix + fenced.encode('ascii'), load.TAG + watch.expected[1])
    positions = []
    for needle in needles:
        hits = [i for i, line in enumerate(lines) if needle in line]
        if len(hits) != 1:
            raise ValueError('missing or repeated seat/load receipt')
        positions.append(hits[0])
    if positions != sorted(set(positions)):
        raise ValueError('seat/load receipts out of order')
    return {'slot': slot, 'registry_index': slot + 2, 'already_controlled': values == existing,
            'local_control_observed': True, 'seat_free_proven': False, 'flight_proven': False,
            'fixture_original_sector_required': True, 'cross_process_identity_proven': False,
            'exact_loaded_file_proven': False}
