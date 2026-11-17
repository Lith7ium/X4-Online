#!/usr/bin/env python3
"""Load one confirmed disposable fixture checkpoint and try one saved seat.

This is a single-process Linux diagnostic. It does not establish steering,
network admission, multiplayer or equivalence of handles between processes.
"""
import argparse
import json
import math
from pathlib import Path
import secrets
import shutil
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'tools/dev')]
from authority.recovery import stage_confirmed_recovery
import authority_fixture_checkpoint_source as fixture_source
import authority_recovery_live as recovery
import authority_saved_fixture_log as fixture_log

CONTROL_TAG = '[X4LAN] AUTH_PLAYER_CONTROL_LIVE '
ACTION_TAG = '[X4LAN] AUTH_PLAYER_CONTROL_MD '
EXPECTED_CONTROL = ('START', 'CREATED', 'BEFORE', 'INTENT_TELEPORT', 'LOCAL_CALL_RETURNED',
                    'DISPATCH', 'FIRST', 'CONTROLLED', 'DONE', 'FENCED')


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise ValueError('private recovery hook missing or ambiguous')
    return text.replace(old, new)


def check_control_log(raw, *, partial):
    if not raw.endswith(b'\n'):
        if partial:
            return False
        raise ValueError('incomplete saved player control log')
    lower = raw.lower()
    if any(error in lower for error in (b'[x4lan] auth_player_control_live error',
            b'error while parsing expression:', b'maximum operator nesting level reached',
            b'could not find suitable data type for conversion!',
            b'invalid data types for arithmetic operation!', b'error in md cue md.x4authority',
            b'error in lua script', b'stack traceback:')):
        raise ValueError('saved player control reported a fault')
    lines = raw.decode('utf-8').splitlines()
    controls = [(index, line.split(CONTROL_TAG, 1)[1].strip())
                for index, line in enumerate(lines) if CONTROL_TAG in line]
    values = tuple(value for _, value in controls)
    if values != EXPECTED_CONTROL[:len(values)]:
        raise ValueError('invalid or inconclusive saved player control receipts')
    pauses = [index for index, line in enumerate(lines) if '[X4LAN] AUTH_RECOVERY PAUSED' in line]
    if controls and (len(pauses) != 1 or controls[0][0] <= pauses[0]):
        raise ValueError('saved player control started before pause')
    actions = [(index, line.split(ACTION_TAG, 1)[1].strip())
               for index, line in enumerate(lines) if ACTION_TAG in line]
    if tuple(value for _, value in actions) not in ((), ('ACTION_BEGIN',), ('ACTION_BEGIN', 'ACTION_RETURNED')):
        raise ValueError('invalid saved player control action markers')
    indices = {value: index for index, value in controls}
    if actions and ('INTENT_TELEPORT' not in indices or actions[0][0] <= indices['INTENT_TELEPORT']):
        raise ValueError('saved player action precedes intent')
    if 'DISPATCH' in indices and (len(actions) != 2 or actions[1][0] >= indices['DISPATCH']):
        raise ValueError('saved player dispatch lacks action markers')
    if values != EXPECTED_CONTROL:
        if partial:
            return False
        raise ValueError('saved player control receipts incomplete')
    return True


class SavedControlWatch(recovery.RecoveryWatch):
    """Add ordered seat observations to the existing marker/pause watcher."""
    def __init__(self, path, marker):
        super().__init__(path, marker)
        self._snapshot = None

    def poll(self):
        captured = fixture_log.capture(self.path, self._snapshot, 32 << 20)
        if captured is None:
            return False
        raw, self._snapshot, caught_up = captured
        self.identity, self.offset = self._snapshot[0], len(raw)
        lines = raw.split(b'\n')
        self.carry = lines.pop()
        if len(self.carry) > self.MAX_LINE or any(len(line) > self.MAX_LINE for line in lines):
            raise ValueError('engine log: line exceeded limit')
        stage = 0
        for line in lines:
            if recovery.RECOVERY in line:
                row = line.split(recovery.RECOVERY, 1)[1].strip()
            elif recovery.MARKER in line:
                row = line.split(recovery.MARKER, 1)[1].strip()
            else:
                continue
            if stage >= 3 or row != self.expected[stage]:
                raise ValueError('engine log: unexpected or out-of-order recovery receipt')
            stage += 1
        self.stage = stage
        validated = self.validate_snapshot(raw)
        return caught_up and not self.carry and stage == 3 and validated

    def validate_snapshot(self, raw):
        return check_control_log(raw, partial=True)


def install(case, profile, scripts, *, slot, nonce, timeout, original_install):
    if slot not in (1, 2) or not math.isfinite(timeout) or not 0 < timeout <= 120:
        raise ValueError('invalid saved player control configuration')
    if set(scripts) != set(fixture_source.SAVED_SCRIPTS):
        raise ValueError('saved MD script set differs')
    config = original_install(case, profile)
    lab = case / 'extensions/x4_lan_lab'
    md, ui = lab / 'md', lab / 'ui'
    for name, contents in scripts.items():
        (md / name).write_bytes(contents)
    extra_md = md / 'authority_saved_player_control.xml'
    shutil.copyfile(ROOT / 'tools/dev/authority_saved_player_control.xml', extra_md)
    extra_ui = []
    for name in ('authority_registry_resolve_string.lua', 'authority_player_control_once.lua',
                 'authority_player_control_live_owner.lua', 'authority_saved_player_control_owner.lua'):
        target = ui / name
        shutil.copyfile(ROOT / 'tools/dev' / name, target)
        extra_ui.append(target)
    marker_probe = ui / 'authority_checkpoint_marker_probe.lua'
    marker_probe.write_text(marker_probe.read_text(encoding='utf-8').replace(
        'X4AuthorityCheckpointMarker', 'X4AuthorityPlayerFixtureMarker'), encoding='utf-8')
    control = ui / 'authority_player_control_once.lua'
    control.write_text(replace_once(control.read_text(encoding='utf-8'),
        'local args={epoch=o.epoch,request_id=o.nonce}',
        'local args={epoch=o.epoch,request_id=o.nonce,slot=o.slot}'), encoding='utf-8')
    owner = ui / 'authority_recovery_probe.lua'
    owner.write_text(replace_once(owner.read_text(encoding='utf-8'), ' if state==\'done\' then return end\n',
        " if state=='done' then X4LAN_AUTHORITY_RECOVERY_EXPERIMENT_TICK();return end\n"), encoding='utf-8')
    manifest = lab / 'ui.xml'
    hook = '    <file name="ui/authority_recovery_probe.lua" />\n'
    additions = ''.join('    <file name="ui/' + path.name + '" />\n' for path in extra_ui)
    manifest.write_text(replace_once(manifest.read_text(encoding='utf-8'), hook, additions + hook), encoding='utf-8')
    text = config.read_text(encoding='ascii')
    if not text.endswith('}\n'):
        raise ValueError('unexpected recovery configuration')
    config.write_text(text[:-2] + ',authority_saved_player_control=true,'
        f'authority_fixture_epoch="{fixture_source.fixture_save.base.archive.REGISTRY_EPOCH}",'
        f'authority_fixture_nonce="{nonce}",authority_fixture_slot={slot},authority_fixture_timeout={timeout:.17g}'
        + '}\n', encoding='ascii')
    return config, [*(md / name for name in scripts), extra_md, *extra_ui]


def run(args):
    if args.slot not in (1, 2) or not math.isfinite(args.timeout) or args.timeout < 60:
        raise ValueError('slot 1 or 2 and at least 60 seconds are required')
    source_store = recovery.base.local_directory(args.store)
    original_stage = recovery.stage_confirmed_recovery
    original_verify = recovery.verify_source
    original_install = recovery.install_probe
    original_watch = recovery.RecoveryWatch
    original_protected = recovery.extra_protected_files
    original_finalizer = recovery.result_finalizer
    saved_scripts = None
    source_checkpoint = None
    verified_profile = None
    extra_files = None
    fixture_nonce = secrets.token_hex(16)

    def stage(store, profile):
        return original_stage(store, profile, marker_script='X4AuthorityPlayerFixtureMarker')

    def verify(store_directory, checkpoint, profile):
        nonlocal saved_scripts, source_checkpoint, verified_profile
        saved_scripts = fixture_source.verify(store_directory, checkpoint, profile)
        source_checkpoint = checkpoint
        verified_profile = profile

    def install_private(case, profile):
        nonlocal extra_files
        if saved_scripts is None:
            raise ValueError('fixture source was not checked')
        config, extra_files = install(case, profile, saved_scripts, slot=args.slot, nonce=fixture_nonce,
                                      timeout=min(120, args.timeout), original_install=original_install)
        return config

    def protected(_case, _profile):
        if extra_files is None:
            raise ValueError('fixture files were not installed')
        return extra_files

    def finalize(result):
        if source_checkpoint is None:
            if result.get('success') is True:
                raise ValueError('fixture source was not checked')
            return
        if fixture_source.verify(source_store, source_checkpoint, verified_profile) != saved_scripts:
            raise ValueError('fixture source changed during recovery')
        result.update(scope='one isolated Linux X4; saved fixture seat observation only',
                      fixture_slot=args.slot, local_control_proven=result.get('success') is True,
                      seat_free_proven=False, flight_proven=False, multiplayer_proven=False)

    try:
        recovery.stage_confirmed_recovery = stage
        recovery.verify_source = verify
        recovery.install_probe = install_private
        recovery.RecoveryWatch = SavedControlWatch
        recovery.extra_protected_files = protected
        recovery.result_finalizer = finalize
        return recovery.run(args)
    finally:
        recovery.stage_confirmed_recovery = original_stage
        recovery.verify_source = original_verify
        recovery.install_probe = original_install
        recovery.RecoveryWatch = original_watch
        recovery.extra_protected_files = original_protected
        recovery.result_finalizer = original_finalizer


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game', type=Path, required=True)
    parser.add_argument('--store', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--display', required=True)
    parser.add_argument('--slot', type=int, choices=(1, 2), required=True)
    parser.add_argument('--timeout', type=float, default=600)
    parser.add_argument('--seed', type=int, default=276944566)
    try:
        result = run(parser.parse_args())
    except (OSError, ValueError, RuntimeError) as error:
        parser.exit(1, 'REFUSED: ' + str(error) + '\n')
    print(json.dumps(result, indent=2))
    return 0 if result['success'] else 1


if __name__ == '__main__':
    sys.exit(main())
