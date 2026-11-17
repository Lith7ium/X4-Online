#!/usr/bin/env python3
"""Two sequential, isolated read-only fixture recoveries and frame reads.

Importing this module does not start X4. This diagnostic compares stationary
anchors, not runtime actor identity, gameplay or universal frame equality.
"""
import argparse
import copy
import json
import math
import re
import secrets
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'tools/dev')]
from authority.checkpoints import CheckpointStore, _read_regular
import authority_fixture_frame_compare as comparison
import authority_recovery_live as recovery
import authority_saved_fixture_log as fixture_log
import authority_saved_player_control_live as seat
import authority_saved_registry_checkpoint_source as source
import authority_fixture_checkpoint_source as fixture_source

SOURCE = ROOT / '.local/private-fixture-restart-overlap-scope-real-20261117-01/overlap-runner/server/checkpoints'
SOURCE_ID = 'checkpoint-cac780ceccbd405ea367dfe028a5ae9d'
SOURCE_SHA = '51191bbc99cca5ebcf319acccde4d48198b30a391bbb0a449fcacde15bda0746'
TAG = b'[X4LAN] AUTH_FIXTURE_FRAME_READ '
MARKER = 'X4AuthorityPlayerFixtureMarker'


def parse_log(raw, nonce, *, partial):
    """Return detached sector rows only for one complete, ordered receipt."""
    if not isinstance(raw, bytes) or not re.fullmatch(r'[0-9a-f]{32}', nonce):
        raise ValueError('invalid frame log context')
    if not raw.endswith(b'\n'):
        if partial: return None
        raise ValueError('incomplete frame log')
    lowered = raw.lower()
    if any(fault in lowered for fault in (b'error while parsing expression:',
            b'maximum operator nesting level reached', b'error in md cue md.x4authority',
            b'error in lua script', b'stack traceback:', b'[x4lan] auth_fixture_frame_read error')):
        raise ValueError('frame reader reported an engine fault')
    rows = []
    pauses = []
    for number, line in enumerate(raw.splitlines()):
        if b'[X4LAN] AUTH_RECOVERY PAUSED' in line: pauses.append(number)
        if TAG in line:
            try: rows.append((number, line.split(TAG, 1)[1].strip().decode('ascii')))
            except UnicodeDecodeError as error: raise ValueError('invalid frame receipt') from error
    if not rows:
        if partial: return None
        raise ValueError('frame receipt missing')
    if len(pauses) != 1 or rows[0][0] <= pauses[0]:
        raise ValueError('frame read preceded recovery pause')
    result = {1: [], 2: []}
    slot, ship_seen, game_time = 1, False, None
    for _, row in rows:
        values = row.split()
        if not values or values[0] not in ('ROW', 'DONE') or len(values) < 4 or values[1] != nonce:
            raise ValueError('foreign or invalid frame receipt')
        if values[2] != str(slot): raise ValueError('frame slot out of order')
        if values[0] == 'ROW':
            if len(values) != 12 or values[3] not in ('ship', 'station'):
                raise ValueError('invalid frame row')
            kind, code, macro, owner, sector = values[3:8]
            try: game, x, y, z = map(float, values[8:12])
            except ValueError as error: raise ValueError('invalid frame number') from error
            if (not all(math.isfinite(value) for value in (game, x, y, z)) or game < 0 or
                    any(abs(value) > 1e9 for value in (x, y, z)) or
                    sector != comparison.FIXTURE_SECTORS[slot]['sector'] or
                    (game_time is not None and game != game_time)):
                raise ValueError('frame time or position differs')
            game_time = game
            if kind == 'ship':
                if (ship_seen or result[slot] or not re.fullmatch(r'[A-Z0-9]+-[0-9]+', code) or
                        macro != 'ship_arg_s_fighter_01_a_macro' or owner != 'player'):
                    raise ValueError('frame fixture ship identity differs')
                ship_seen = True
            else:
                if not ship_seen: raise ValueError('frame station before ship')
                result[slot].append({'code':code, 'macro':macro, 'owner':owner,
                                     'sector':sector, 'position':[x, y, z]})
                if len(result[slot]) > len(comparison.FIXTURE_SECTORS[slot]['stations']):
                    raise ValueError('too many frame stations')
        else:
            if len(values) != 5 or not values[3].isdigit(): raise ValueError('invalid frame completion')
            try: done_time = float(values[4])
            except ValueError as error: raise ValueError('invalid frame completion time') from error
            if (not ship_seen or int(values[3]) != len(result[slot]) or len(result[slot]) < 3 or
                    not math.isfinite(done_time) or done_time != game_time):
                raise ValueError('frame completion differs')
            slot += 1; ship_seen = False
    if slot != 3:
        if partial: return None
        raise ValueError('frame observations incomplete')
    # Reuse the same identity, finite position and geometry validation even
    # before a second process is compared; this does not prove a shared frame.
    comparison.compare(result, result)
    return result


def install(case, profile, scripts, *, nonce, original_install):
    if set(scripts) != set(fixture_source.SAVED_SCRIPTS):
        raise ValueError('saved fixture scripts differ')
    config = original_install(case, profile)
    lab = case / 'extensions/x4_lan_lab'; ui = lab / 'ui'; md = lab / 'md'
    for name, contents in scripts.items(): (md / name).write_bytes(contents)
    for name in ('authority_fixture_frame_read.xml',):
        shutil.copyfile(ROOT / 'tools/dev' / name, md / name)
    for name in ('authority_registry_resolve_string.lua', 'authority_fixture_frame_read.lua'):
        shutil.copyfile(ROOT / 'tools/dev' / name, ui / name)
    marker = ui / 'authority_checkpoint_marker_probe.lua'
    text = marker.read_text(encoding='utf-8')
    if 'X4AuthorityCheckpointMarker' not in text: raise ValueError('fixture marker hook unavailable')
    marker.write_text(text.replace('X4AuthorityCheckpointMarker', MARKER), encoding='utf-8')
    owner = ui / 'authority_recovery_probe.lua'
    owner.write_text(seat.replace_once(owner.read_text(encoding='utf-8'),
        " if state=='done' then return end\n",
        " if state=='done' then X4LAN_AUTHORITY_RECOVERY_EXPERIMENT_TICK();return end\n"), encoding='utf-8')
    manifest = lab / 'ui.xml'
    hook = '    <file name="ui/authority_recovery_probe.lua" />\n'
    manifest.write_text(seat.replace_once(manifest.read_text(encoding='utf-8'), hook,
        '    <file name="ui/authority_registry_resolve_string.lua" />\n'
        '    <file name="ui/authority_fixture_frame_read.lua" />\n' + hook), encoding='utf-8')
    text = config.read_text(encoding='ascii')
    if not text.endswith('}\n'): raise ValueError('unexpected recovery configuration')
    epoch = fixture_source.fixture_save.base.archive.REGISTRY_EPOCH
    config.write_text(text[:-2] + ',authority_frame_enabled=true,'
        f'authority_frame_epoch="{epoch}",authority_frame_nonce="{nonce}"' + '}\n', encoding='ascii')
    return config, [*(md / name for name in scripts), md / 'authority_fixture_frame_read.xml',
                    ui / 'authority_registry_resolve_string.lua', ui / 'authority_fixture_frame_read.lua']


def run_one(args, out):
    nonce = secrets.token_hex(16)
    original = (recovery.stage_confirmed_recovery, recovery.verify_source, recovery.install_probe,
                recovery.RecoveryWatch, recovery.extra_protected_files, recovery.observation_callback,
                recovery.result_finalizer)
    scripts = checkpoint = extra = profile_path = None
    observed = [None]

    class FrameWatch(original[3]):
        def __init__(self, path, marker):
            super().__init__(path, marker); self.snapshot = None
        def poll(self):
            caught = super().poll()
            captured = fixture_log.capture(self.path, self.snapshot, 32 << 20)
            if captured is None: return False
            raw, self.snapshot, stable = captured
            parsed = parse_log(raw, nonce, partial=True)
            if parsed is not None:
                if observed[0] is not None and observed[0] != parsed:
                    raise ValueError('frame evidence changed')
                observed[0] = parsed
            return caught and stable and self.stage == 3 and parsed is not None

    def stage(store, profile): return original[0](store, profile, marker_script=MARKER)
    def verify(store, selected, profile):
        nonlocal scripts, checkpoint, profile_path
        if selected.checkpoint_id != SOURCE_ID or selected.sha256 != SOURCE_SHA:
            raise ValueError('fixture frame checkpoint differs')
        scripts = source.verify_recovered(store, selected, profile)
        checkpoint, profile_path = selected, profile
    def install_private(case, profile):
        nonlocal extra
        if scripts is None: raise ValueError('fixture source not verified')
        config, extra = install(case, profile, scripts, nonce=nonce, original_install=original[2])
        return config
    def protected(_case, _profile):
        if extra is None: raise ValueError('fixture frame files not installed')
        return extra
    def capture(*, guard, identity, **_kwargs):
        if guard() is not None: raise ValueError('unexpected recovery guard result')
        if observed[0] is None: raise ValueError('frame observations unavailable')
        if (type(identity) is not tuple or len(identity) != 2 or
                any(type(value) is not int or value <= 0 for value in identity)):
            raise ValueError('owned X4 identity unavailable')
        return {'stations':copy.deepcopy(observed[0]), 'x4_identity':list(identity)}
    def final(result):
        if result.get('success') is not True: return
        if checkpoint is None or observed[0] is None or source.verify_recovered(args.store, checkpoint, profile_path) != scripts:
            raise ValueError('fixture source or frame observations changed')
        result.update(scope='one isolated paused Linux X4; read-only fixture station frames',
                      native_frame_read_observed=True, continuous_pause_proven=False,
                      exact_loaded_file_proven=False, cross_process_identity_proven=False)
    try:
        (recovery.stage_confirmed_recovery, recovery.verify_source, recovery.install_probe,
         recovery.RecoveryWatch, recovery.extra_protected_files, recovery.observation_callback,
         recovery.result_finalizer) = (stage, verify, install_private, FrameWatch, protected, capture, final)
        return recovery.run(SimpleNamespace(game=args.game, store=args.store, out=out, display=args.display,
                                            timeout=args.timeout, seed=args.seed))
    finally:
        (recovery.stage_confirmed_recovery, recovery.verify_source, recovery.install_probe,
         recovery.RecoveryWatch, recovery.extra_protected_files, recovery.observation_callback,
         recovery.result_finalizer) = original


def run(args):
    if Path(args.store).resolve(strict=True) != SOURCE.resolve(strict=True):
        raise ValueError('only the pinned confirmed fixture source is permitted')
    out = recovery.snapshot.output_path(args.out)
    out.mkdir(mode=0o700, parents=True, exist_ok=False)
    result = {'success':False, 'scope':'two sequential isolated read-only Linux X4 recoveries',
              'gameplay_proven':False, 'cross_process_identity_proven':False,
              'universal_frame_identity_proven':False, 'continuous_pause_proven':False}
    try:
        observations = []; identities = []
        for index in (1, 2):
            child = run_one(args, out / ('read-%d' % index))
            if (child.get('success') is not True or child.get('owned_processes_remaining') != [] or
                    child.get('checkpoint_id') != SOURCE_ID or child.get('sha256') != SOURCE_SHA or
                    child.get('native_frame_read_observed') is not True):
                raise ValueError('read-only fixture recovery was not confirmed')
            observations.append(child['experiment']['stations'])
            identity = child['experiment']['x4_identity']
            if (type(identity) is not list or len(identity) != 2 or
                    any(type(value) is not int or value <= 0 for value in identity)):
                raise ValueError('fixture process identity unavailable')
            identities.append(tuple(identity))
        if identities[0] == identities[1]: raise ValueError('fixture recoveries reused an X4 process')
        result['comparison'] = comparison.compare(observations[0], observations[1])
        result.update(success=True, source_checkpoint_id=SOURCE_ID, source_sha256=SOURCE_SHA,
                      two_sequential_native_reads=True, actual_loaded_bytes_proven=False)
    except (Exception, KeyboardInterrupt) as error:
        result['error'] = str(error) or type(error).__name__
    (out / 'result.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game', type=Path, required=True); parser.add_argument('--display', required=True)
    parser.add_argument('--out', type=Path, required=True); parser.add_argument('--store', type=Path, default=SOURCE)
    parser.add_argument('--timeout', type=float, default=600); parser.add_argument('--seed', type=int, default=276944566)
    try: result = run(parser.parse_args())
    except (OSError, ValueError, RuntimeError) as error: parser.exit(1, 'REFUSED: ' + str(error) + '\n')
    print(json.dumps(result, indent=2)); return 0 if result['success'] else 1


if __name__ == '__main__': sys.exit(main())
